# Security Guide

## Credential Management

### NEVER Commit Passwords

Do NOT put passwords in:
- `config.json`
- Source code files
- Documentation (except examples marked as "development only")

### Environment Variables (Recommended)

Set credentials via environment variables:

```bash
# Required
export ARANGO_ROOT_PASSWORD=your_secure_password

# Optional overrides
export ARANGO_HOST=localhost
export ARANGO_PORT=8529
export ARANGO_USERNAME=root
export ARANGO_DATABASE=entity_resolution
```

### Configuration Files

Use `config.example.json` as a template:

```bash
# Copy example config
cp config.example.json config.json

# Edit config.json (already in .gitignore)
# Leave password empty - it will be read from environment
```

### Development/Testing Only

The library NEVER hardcodes a password fallback. A password must always be
supplied via the environment (`ARANGO_PASSWORD` or `ARANGO_ROOT_PASSWORD`);
if neither is set, configuration loading fails fast with an error.

For local development you provide the password explicitly. The optional
`USE_DEFAULT_PASSWORD=true` flag does NOT supply a password -- it only emits a
warning to make local-development mode obvious:

```bash
export ARANGO_ROOT_PASSWORD=your_local_dev_password   # required
export USE_DEFAULT_PASSWORD=true                       # optional: warns that this is local-dev mode
```

[WARNING] NEVER use development passwords in production!

### Web UI and MCP SSE authentication

The optional Web UI (`arango-er ui`) and the MCP SSE transport
(`arango-er-mcp --transport sse`) expose the database through a network
service. Both bind to `127.0.0.1` by default and refuse to bind to a
non-loopback host without a shared-secret token:

```bash
# UI
export ER_UI_AUTH_TOKEN=$(openssl rand -hex 32)
arango-er ui --serve-host 0.0.0.0            # requires the token above

# MCP SSE
export ER_MCP_AUTH_TOKEN=$(openssl rand -hex 32)
arango-er-mcp --transport sse --host 0.0.0.0 # requires the token above
```

Clients must send `Authorization: Bearer <token>` (the UI also accepts
`X-API-Key`, and WebSocket clients may pass `?token=<token>`). Binding to a
public interface without a token requires an explicit `--insecure` override.

---

## Production Deployment

### Use Secrets Management

For production, use a secrets management system:

**AWS Secrets Manager:**
```python
import boto3

client = boto3.client('secretsmanager')
secret = client.get_secret_value(SecretId='arangodb/password')
os.environ['ARANGO_ROOT_PASSWORD'] = secret['SecretString']
```

**HashiCorp Vault:**
```python
import hvac

client = hvac.Client(url='https://vault.example.com')
secret = client.secrets.kv.v2.read_secret_version(path='arangodb/password')
os.environ['ARANGO_ROOT_PASSWORD'] = secret['data']['data']['password']
```

**Kubernetes Secrets:**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: arangodb-credentials
type: Opaque
stringData:
  password: your_secure_password
```

---

## Security Best Practices

### 1. Password Requirements

- Minimum 16 characters
- Mix of uppercase, lowercase, numbers, symbols
- Not in common password lists
- Rotated regularly (every 90 days)

### 2. Network Security

- Use HTTPS/TLS for all connections
- Enable SSL certificate verification
- Use VPN or private networks
- Restrict database access to application servers only

### 3. Access Control

- Use dedicated service accounts (not root)
- Grant minimum required permissions
- Enable audit logging
- Monitor for suspicious activity

### 4. ArangoDB Security

Enable authentication:
```yaml
# docker-compose.yml
environment:
  ARANGO_NO_AUTH: false  # ALWAYS false in production
  ARANGO_ROOT_PASSWORD: ${ARANGO_ROOT_PASSWORD}
```

Create application user:
```javascript
// In ArangoDB console
db._createDatabase('entity_resolution');
db._useDatabase('entity_resolution');

const users = require('@arangodb/users');
users.save('er_service_user', 'strong_password', true);
users.grantDatabase('er_service_user', 'entity_resolution', 'rw');
```

---

## Security Checklist

Before deployment, verify:

- [ ] No passwords in source code
- [ ] No passwords in config files (config.json in .gitignore)
- [ ] Environment variables set correctly
- [ ] Using secrets management in production
- [ ] TLS/SSL enabled
- [ ] Authentication enabled (ARANGO_NO_AUTH=false)
- [ ] Dedicated service account (not root)
- [ ] Network access restricted
- [ ] Audit logging enabled
- [ ] Dependency vulnerabilities checked

---

## Incident Response

If credentials are exposed:

1. **IMMEDIATE:** Rotate all affected passwords
2. **IMMEDIATE:** Revoke exposed credentials
3. **URGENT:** Check audit logs for unauthorized access
4. **URGENT:** Notify security team
5. **FOLLOW-UP:** Review how exposure occurred
6. **FOLLOW-UP:** Update procedures to prevent recurrence

---

## Security Contact

For security issues:
- Create a GitHub issue tagged "security"
- Or email: security@your-organization.com

---

## Compliance

This system handles potentially sensitive data. Ensure compliance with:
- GDPR (if processing EU citizen data)
- CCPA (if processing California resident data)
- HIPAA (if processing health data)
- PCI-DSS (if processing payment data)
- SOC 2 (for enterprise deployments)

---

**Last Updated:** 2025-01-04  
**Review Frequency:** Quarterly

