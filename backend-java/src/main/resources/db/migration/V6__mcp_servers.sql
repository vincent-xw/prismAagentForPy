CREATE TABLE IF NOT EXISTS mcp_servers (
    id           CHAR(36)     NOT NULL,
    name         VARCHAR(64)  NOT NULL,
    slug         VARCHAR(64)  NOT NULL,
    transport    VARCHAR(16)  NOT NULL,
    command      TEXT         NULL,
    args_json    JSON         NULL,
    env_json     JSON         NULL,
    url          TEXT         NULL,
    headers_json JSON         NULL,
    enabled      TINYINT(1)   NOT NULL DEFAULT 0,
    status       VARCHAR(16)  NOT NULL DEFAULT 'disabled',
    last_error   TEXT         NULL,
    created_at   DATETIME(6)  NOT NULL,
    updated_at   DATETIME(6)  NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY ux_mcp_servers_name (name),
    UNIQUE KEY ux_mcp_servers_slug (slug)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;
