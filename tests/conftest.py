"""
Pytest Configuration and Shared Fixtures

Provides common fixtures and configuration for all tests.
"""

import pytest
import os
import sys
from typing import Dict, Any

# Prevent litellm from auto-loading a developer .env into os.environ at import
# time. litellm calls load_dotenv() on import when LITELLM_MODE=DEV (its
# default), which otherwise leaks local values (e.g. ARANGO_ENDPOINT) into
# env-reading unit tests and causes order-dependent failures. Must be set
# before any import that may transitively import litellm.
os.environ.setdefault("LITELLM_MODE", "PRODUCTION")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from entity_resolution.utils.config import Config, get_config
from entity_resolution.services.bulk_blocking_service import BulkBlockingService

# Ensure unit tests don't fail due to missing environment variables
os.environ.setdefault("USE_DEFAULT_PASSWORD", "true")
os.environ.setdefault("ARANGO_ROOT_PASSWORD", "testpassword123")


@pytest.fixture(autouse=True)
def _restore_environ():
    """Snapshot and restore os.environ around every test.

    Prevents env mutations (including values a test may read from a developer's
    local .env file, e.g. ARANGO_ENDPOINT) from leaking into later tests, which
    previously caused order-dependent failures in env-reading unit tests.
    """
    saved = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


# Configure pytest
def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (require database)"
    )
    config.addinivalue_line(
        "markers", "performance: marks tests as performance tests (slow)"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests (fast, no dependencies)"
    )


# Fixtures for configuration
@pytest.fixture(scope="session")
def test_config():
    """Provide test configuration"""
    # Ensure we have a valid config for unit tests without environment lookups
    # setting USE_DEFAULT_PASSWORD=true makes get_config() not fail
    os.environ["USE_DEFAULT_PASSWORD"] = "true"
    config = get_config()
    
    # Override with test-specific settings
    config.db.database = os.getenv("TEST_DB_NAME", "entity_resolution_test")
    
    return config


def _find_labelled_container() -> tuple[str | None, str | None, str | None]:
    """
    Look for a running ArangoDB container labelled 'entity-resolution-test=true'.

    Returns (host, port, password) or (None, None, None).
    """
    try:
        import subprocess, json
        out = subprocess.check_output(
            ["docker", "ps", "--filter", "label=entity-resolution-test=true",
             "--format", "{{json .}}"],
            text=True, timeout=5,
        )
        for line in out.strip().splitlines():
            meta = json.loads(line)
            ports = meta.get("Ports", "")
            # e.g. "0.0.0.0:49876->8529/tcp"
            for part in ports.split(","):
                part = part.strip()
                if "->8529" in part:
                    host_part = part.split("->")[0].strip()
                    host, port = host_part.rsplit(":", 1)
                    host = "localhost" if host in ("0.0.0.0", "::") else host
                    # Password stored as label entity-resolution-test-password
                    inspect = subprocess.check_output(
                        ["docker", "inspect", meta["ID"]],
                        text=True, timeout=5,
                    )
                    info = json.loads(inspect)[0]
                    labels = info.get("Config", {}).get("Labels", {})
                    password = labels.get("entity-resolution-test-password", "openSesame")
                    return host, port, password
    except Exception:
        pass
    return None, None, None


def _start_arango_container() -> tuple[str, str, str, str]:
    """
    Spin up a fresh arangodb:3.12 Docker container for the test session.

    Returns (container_id, host, port, password).
    """
    import subprocess, time, random, string

    password = "er_test_" + "".join(random.choices(string.ascii_lowercase, k=10))
    label = "entity-resolution-test=true"
    label_pw = f"entity-resolution-test-password={password}"

    result = subprocess.check_output(
        [
            "docker", "run", "-d", "--rm",
            "-p", "0:8529",  # random host port
            "-e", f"ARANGO_ROOT_PASSWORD={password}",
            "-l", label,
            "-l", label_pw,
            "arangodb/arangodb:3.12",
        ],
        text=True, timeout=30,
    )
    container_id = result.strip()

    # Find the assigned host port
    port_out = subprocess.check_output(
        ["docker", "port", container_id, "8529"],
        text=True, timeout=10,
    ).strip()
    # format: "0.0.0.0:NNNNN"
    host_port = port_out.split(":")[-1].strip()

    # Wait up to 30 s for ArangoDB to be ready
    from arango import ArangoClient
    for attempt in range(60):
        try:
            client = ArangoClient(hosts=f"http://localhost:{host_port}")
            sys_db = client.db("_system", username="root", password=password)
            sys_db.properties()
            break
        except Exception:
            time.sleep(0.5)
    else:
        subprocess.run(["docker", "stop", container_id], timeout=15)
        raise RuntimeError("ArangoDB container did not become ready in 30 s")

    return container_id, "localhost", host_port, password


@pytest.fixture(scope="session")
def db_connection(test_config):
    """
    Provide a database connection for integration/ANN tests.

    Connection resolution order:
    1. Explicit env vars: ARANGO_TEST_HOST, ARANGO_TEST_PORT, ARANGO_TEST_PASSWORD
    2. A running Docker container labelled 'entity-resolution-test=true'
    3. Spin up a fresh arangodb:3.12 Docker container on demand (torn down at end)
    """
    from arango import ArangoClient

    managed_container: str | None = None
    db_name = os.getenv("TEST_DB_NAME", "entity_resolution_test")

    # --- Tier 1: explicit env vars ---
    host = os.getenv("ARANGO_TEST_HOST")
    port = os.getenv("ARANGO_TEST_PORT")
    password = os.getenv("ARANGO_TEST_PASSWORD")

    if not (host and port and password):
        # --- Tier 2: labelled container ---
        host, port, password = _find_labelled_container()

    if not (host and port and password):
        # --- Tier 3: spin one up ---
        try:
            managed_container, host, port, password = _start_arango_container()
        except Exception as e:
            pytest.skip(f"Could not start ArangoDB Docker container: {e}")
            return

    client = ArangoClient(hosts=f"http://{host}:{port}")
    try:
        sys_db = client.db("_system", username="root", password=password)
        # Create test database if it doesn't exist
        if not sys_db.has_database(db_name):
            sys_db.create_database(db_name)
        db = client.db(db_name, username="root", password=password)
        db.properties()  # validate connection
    except Exception as e:
        if managed_container:
            import subprocess
            subprocess.run(["docker", "stop", managed_container], timeout=15)
        pytest.skip(f"Cannot connect to ArangoDB at {host}:{port}: {e}")
        return

    yield db

    # Cleanup
    if managed_container:
        import subprocess
        subprocess.run(["docker", "stop", managed_container], timeout=15)



# Fixtures for test data
@pytest.fixture
def sample_customers():
    """Provide sample customer records for testing"""
    return [
        {
            "_key": "1",
            "first_name": "John",
            "last_name": "Smith",
            "email": "john.smith@example.com",
            "phone": "555-1234",
            "address": "123 Main St",
            "city": "Boston",
            "company": "Acme Corp"
        },
        {
            "_key": "2",
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane.doe@example.com",
            "phone": "555-5678",
            "address": "456 Oak Ave",
            "city": "New York",
            "company": "TechCo"
        },
        {
            "_key": "3",
            "first_name": "John",
            "last_name": "Smith",  # Duplicate
            "email": "j.smith@example.com",
            "phone": "555-1234",  # Same phone
            "address": "123 Main Street",  # Slightly different address
            "city": "Boston",
            "company": "Acme Corporation"
        }
    ]


@pytest.fixture
def sample_candidate_pairs():
    """Provide sample candidate pairs for testing"""
    return [
        {
            "record_a_id": "customers/1",
            "record_b_id": "customers/2",
            "strategy": "exact_phone",
            "blocking_key": "555-1234"
        },
        {
            "record_a_id": "customers/1",
            "record_b_id": "customers/3",
            "strategy": "ngram_name",
            "blocking_key": "JOH_2"
        }
    ]


# Fixtures for services
@pytest.fixture
def bulk_service(test_config):
    """Provide BulkBlockingService instance"""
    service = BulkBlockingService(test_config)
    return service


@pytest.fixture
def connected_bulk_service(bulk_service):
    """Provide connected BulkBlockingService"""
    if not bulk_service.connect():
        pytest.skip("Cannot connect to database")
    return bulk_service


# Fixtures for test collections
@pytest.fixture
def temp_collection(db_connection):
    """Create a temporary collection for testing"""
    import uuid
    
    collection_name = f"test_temp_{uuid.uuid4().hex[:8]}"
    
    # Create collection
    if db_connection.has_collection(collection_name):
        db_connection.delete_collection(collection_name)
    
    collection = db_connection.create_collection(collection_name)
    
    yield collection_name
    
    # Cleanup
    if db_connection.has_collection(collection_name):
        db_connection.delete_collection(collection_name)


@pytest.fixture
def populated_collection(db_connection, temp_collection, sample_customers):
    """Create and populate a test collection"""
    collection = db_connection.collection(temp_collection)
    collection.insert_many(sample_customers)
    
    return temp_collection


# Helper functions
def assert_valid_result(result: Dict[str, Any]):
    """Assert that a result dictionary is valid"""
    assert isinstance(result, dict)
    assert 'success' in result
    
    if result['success']:
        assert 'candidate_pairs' in result or 'clusters' in result
    else:
        assert 'error' in result


def assert_valid_statistics(stats: Dict[str, Any]):
    """Assert that statistics dictionary is valid"""
    assert isinstance(stats, dict)
    assert 'execution_time' in stats
    assert stats['execution_time'] >= 0
    
    if 'total_pairs' in stats:
        assert stats['total_pairs'] >= 0
    
    if 'pairs_per_second' in stats:
        assert stats['pairs_per_second'] >= 0


# Pytest hooks for better output
def pytest_collection_modifyitems(config, items):
    """Modify test items to add markers based on test name/location"""
    for item in items:
        # Add markers based on test file name
        if "integration" in item.nodeid:
            item.add_marker(pytest.mark.integration)
        elif "performance" in item.nodeid or "benchmark" in item.nodeid:
            item.add_marker(pytest.mark.performance)
        else:
            item.add_marker(pytest.mark.unit)


def pytest_report_header(config):
    """Add custom header to pytest output"""
    env_info = [
        "Test Environment:",
        f"  Database: {os.getenv('ARANGO_DATABASE', 'entity_resolution_test')}",
        f"  Host: {os.getenv('ARANGO_HOST', 'localhost')}:{os.getenv('ARANGO_PORT', '8529')}",
        f"  Skip Integration: {os.getenv('SKIP_INTEGRATION_TESTS', 'false')}",
        f"  Skip Performance: {os.getenv('SKIP_PERFORMANCE_TESTS', 'false')}",
    ]
    return env_info

