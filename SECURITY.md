# SECURITY.md

## Security Architecture

The Discovery Studio MCP server implements security at multiple layers.

### 1. Path Validation

All file paths are:
- Resolved to absolute paths
- Checked against the configured allowed input directories (DS_ALLOWED_INPUT_DIRS)
- Output path must be within the configured output directory (DS_OUTPUT_DIR)
- Path traversal attacks are blocked (backslash, ../ sanitization)

### 2. File Extension Whitelist

Only known scientific file extensions are accepted:
`.pdb`, `.mol`, `.mol2`, `.sdf`, `.sd`, `.msv`, `.dsv`, `.cif`, `.dsx`,
`.csv`, `.car`, `.msi`, `.xyz`, `.smi`, `.txt`, `.log`, `.json`, `.png`, `.jpg`

Executable and script extensions (`.exe`, `.bat`, `.sh`, `.py`, `.pl`, `.dll`, `.so`) are rejected.

### 3. File Size Limits

Configurable via `DS_MAX_FILE_SIZE_MB` (default 500 MB). Files exceeding this limit are rejected.

### 4. Output Isolation

All results are written to the workspace directory (`DS_OUTPUT_DIR`/workspace/jobs/<job_id>/).
The server never overwrites files outside this directory.

### 5. No Arbitrary Code Execution

The server does NOT provide tools for:
- Executing arbitrary Perl code
- Executing arbitrary Python code
- Running shell commands
- Executing PowerShell scripts

### 6. Protocol Whitelist

Only explicitly registered protocols can be executed. Unknown protocols are rejected
with a descriptive error.

### 7. Destructive Action Confirmation

Operations that could modify or delete data require `confirm_destructive_action: true`.

### 8. Job Isolation

Each job runs in a separate subdirectory:
```
workspace/jobs/<job_id>/
  input/
  output/
  logs/
  manifest.json
```

### 9. Secret Masking

- No passwords, tokens, or license keys are ever logged
- Environment variable values containing sensitive keywords are redacted
- Pipeline Pilot credentials are never included in manifest files

### 10. Logging

- All tool calls are logged with timestamps
- Parameter values over 200 characters are truncated in logs
- Sensitive parameter names containing "password", "token", "secret", "key" are redacted

### 11. Manifest Reproducibility

Every job creates a `manifest.json` containing:
- Protocol name and parameters
- File hashes (input and output)
- Timestamps
- Version information
- Adapter name and version
- No credentials or secrets

### Security Checklist for Deployment

- [ ] Set DS_ALLOWED_INPUT_DIRS to specific directories only
- [ ] Set DS_MOCK_MODE=false for production
- [ ] Configure allowed input directories with minimal scope
- [ ] Set DS_MAX_FILE_SIZE_MB to appropriate limit
- [ ] Set DS_JOB_TIMEOUT_SECONDS to prevent runaway jobs
- [ ] Set DS_MAX_CONCURRENT_JOBS to 1 for deterministic execution
- [ ] Keep DS_ENABLE_UI_FALLBACK=false (use only if documented and understood)
- [ ] Review log files periodically for anomalies
- [ ] Run health check after configuration changes
