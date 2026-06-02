"""
Input validation utilities for security.

Provides validation functions to prevent AQL injection and ensure
data integrity when accepting user input for collection names, field names,
and other database identifiers.
"""

import re
from typing import List, Optional


def validate_collection_name(name: str) -> str:
    """
    Validate collection name to prevent AQL injection.
    
    Collection names in ArangoDB can only contain letters, digits, and underscores.
    They must start with a letter and be between 1-256 characters.
    
    Args:
        name: Collection name to validate
        
    Returns:
        The validated collection name
        
    Raises:
        ValueError: If name contains invalid characters or is invalid format
        
    Examples:
        >>> validate_collection_name("companies")
        'companies'
        >>> validate_collection_name("test_collection_123")
        'test_collection_123'
        >>> validate_collection_name("'; DROP TABLE")
        Traceback (most recent call last):
        ValueError: Invalid collection name...
    """
    if not name:
        raise ValueError("Collection name cannot be empty")
    
    if not isinstance(name, str):
        raise ValueError(f"Collection name must be a string, got {type(name)}")
    
    # Must start with a letter
    if not name[0].isalpha():
        raise ValueError(
            f"Invalid collection name: '{name}'. "
            "Collection names must start with a letter."
        )
    
    # Only alphanumeric and underscores allowed
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', name):
        raise ValueError(
            f"Invalid collection name: '{name}'. "
            "Only letters, digits, and underscores allowed (must start with letter)."
        )
    
    # Length check
    if len(name) > 256:
        raise ValueError(
            f"Collection name too long: {len(name)} characters (max 256)"
        )
    
    # Reject system collection prefix (reserved)
    if name.startswith('_'):
        raise ValueError(
            f"Invalid collection name: '{name}'. "
            "Names starting with underscore are reserved for system collections."
        )
    
    return name


def validate_field_name(name: str, allow_nested: bool = True) -> str:
    """
    Validate field name to prevent AQL injection.
    
    Field names can contain letters, digits, and underscores.
    If allow_nested=True, dots are allowed for nested field access (e.g., 'address.city').
    
    Args:
        name: Field name to validate
        allow_nested: Whether to allow dots for nested fields (default: True)
        
    Returns:
        The validated field name
        
    Raises:
        ValueError: If name contains invalid characters
        
    Examples:
        >>> validate_field_name("first_name")
        'first_name'
        >>> validate_field_name("address.city")
        'address.city'
        >>> validate_field_name("address.city", allow_nested=False)
        Traceback (most recent call last):
        ValueError: Invalid field name...
    """
    if not name:
        raise ValueError("Field name cannot be empty")
    
    if not isinstance(name, str):
        raise ValueError(f"Field name must be a string, got {type(name)}")
    
    # Pattern depends on whether nested fields are allowed
    if allow_nested:
        # Allow dots for nested fields (e.g., address.city.zipcode)
        pattern = r'^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*$'
        error_msg = "Only letters, digits, underscores, and dots (for nested fields) allowed."
    else:
        pattern = r'^[a-zA-Z_][a-zA-Z0-9_]*$'
        error_msg = "Only letters, digits, and underscores allowed."
    
    if not re.match(pattern, name):
        raise ValueError(
            f"Invalid field name: '{name}'. {error_msg}"
        )
    
    # Length check
    if len(name) > 256:
        raise ValueError(
            f"Field name too long: {len(name)} characters (max 256)"
        )
    
    return name


def validate_field_names(names: List[str], allow_nested: bool = True) -> List[str]:
    """
    Validate multiple field names.
    
    Args:
        names: List of field names to validate
        allow_nested: Whether to allow dots for nested fields
        
    Returns:
        List of validated field names
        
    Raises:
        ValueError: If any name is invalid
    """
    if not isinstance(names, list):
        raise ValueError(f"Field names must be a list, got {type(names)}")
    
    validated = []
    for name in names:
        validated.append(validate_field_name(name, allow_nested=allow_nested))
    
    return validated


# AQL keywords that must never appear in a config-supplied computed-field
# expression. These enable data modification, sub-queries, or statement
# break-out that could turn a "computed field" into an injection vector.
_FORBIDDEN_EXPRESSION_KEYWORDS = (
    "INSERT",
    "UPDATE",
    "UPSERT",
    "REPLACE",
    "REMOVE",
    "LET",
    "COLLECT",
    "INTO",
    "FOR",
    "RETURN",
    "WITH",
)


def validate_computed_field_expression(expression: str) -> str:
    """
    Validate a config-supplied AQL computed-field expression.

    Computed-field expressions are interpolated directly into generated AQL
    (``LET tmp = <expression>``), so an attacker who controls the pipeline
    config could otherwise inject data-modification or sub-query statements.
    This validator rejects expressions that contain data-modification
    keywords, sub-queries, comment sequences, or statement break-out.

    Safe expressions (``CONCAT(d.first, d.last)``, ``LOWER(d.name)``,
    ``SUBSTRING(d.code, 0, 3)``) pass unchanged.

    Args:
        expression: The AQL expression to validate.

    Returns:
        The validated expression (stripped).

    Raises:
        ValueError: If the expression contains forbidden constructs.
    """
    if not isinstance(expression, str):
        raise ValueError(
            f"Computed-field expression must be a string, got {type(expression)}"
        )

    expr = expression.strip()
    if not expr:
        raise ValueError("Computed-field expression cannot be empty")

    # Reject comment sequences which could be used to comment out the rest of
    # the generated query.
    if "//" in expr or "/*" in expr or "*/" in expr:
        raise ValueError(
            f"Invalid computed-field expression: '{sanitize_string_for_display(expr)}'. "
            "Comment sequences are not allowed."
        )

    # Reject statement separators.
    if ";" in expr:
        raise ValueError(
            f"Invalid computed-field expression: '{sanitize_string_for_display(expr)}'. "
            "Statement separators (';') are not allowed."
        )

    upper = expr.upper()
    for keyword in _FORBIDDEN_EXPRESSION_KEYWORDS:
        if re.search(rf"\b{keyword}\b", upper):
            raise ValueError(
                f"Invalid computed-field expression: "
                f"'{sanitize_string_for_display(expr)}'. "
                f"The AQL keyword '{keyword}' is not allowed in computed fields."
            )

    return expr


def validate_graph_name(name: str) -> str:
    """
    Validate graph name to prevent AQL injection.
    
    Graph names follow the same rules as collection names.
    
    Args:
        name: Graph name to validate
        
    Returns:
        The validated graph name
        
    Raises:
        ValueError: If name is invalid
    """
    # Graphs follow same naming rules as collections
    return validate_collection_name(name)


def validate_view_name(name: str) -> str:
    """
    Validate ArangoSearch view name to prevent AQL injection.
    
    View names follow the same rules as collection names.
    
    Args:
        name: View name to validate
        
    Returns:
        The validated view name
        
    Raises:
        ValueError: If name is invalid
    """
    # Views follow same naming rules as collections
    return validate_collection_name(name)


def validate_database_name(name: str) -> str:
    """
    Validate database name.
    
    Database names can contain letters, digits, underscores, and hyphens.
    They must start with a letter and be between 1-64 characters.
    
    Args:
        name: Database name to validate
        
    Returns:
        The validated database name
        
    Raises:
        ValueError: If name is invalid
    """
    if not name:
        raise ValueError("Database name cannot be empty")
    
    if not isinstance(name, str):
        raise ValueError(f"Database name must be a string, got {type(name)}")
    
    # Must start with a letter
    if not name[0].isalpha():
        raise ValueError(
            f"Invalid database name: '{name}'. "
            "Database names must start with a letter."
        )
    
    # Only alphanumeric, underscores, and hyphens
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', name):
        raise ValueError(
            f"Invalid database name: '{name}'. "
            "Only letters, digits, underscores, and hyphens allowed (must start with letter)."
        )
    
    # Length check (ArangoDB limit is 64)
    if len(name) > 64:
        raise ValueError(
            f"Database name too long: {len(name)} characters (max 64)"
        )
    
    return name


def sanitize_string_for_display(value: str, max_length: int = 100) -> str:
    """
    Sanitize a string for safe display in logs/errors.
    
    Prevents log injection by removing control characters and limiting length.
    
    Args:
        value: String to sanitize
        max_length: Maximum length for display
        
    Returns:
        Sanitized string safe for display
    """
    if not isinstance(value, str):
        value = str(value)
    
    # Remove control characters except newline/tab
    sanitized = ''.join(
        char if (char.isprintable() or char in '\n\t') else '?'
        for char in value
    )
    
    # Truncate if too long
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + '...'
    
    return sanitized

