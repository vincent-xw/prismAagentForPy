-- Phase 1 基线：工作区与会话。字段语义与 Python V1.4 对齐，类型按 MySQL 惯例落库。
CREATE TABLE workspaces (
    id            CHAR(36)     NOT NULL,
    root_path     VARCHAR(768) NOT NULL,
    label         VARCHAR(255) NULL,
    is_active     TINYINT(1)   NOT NULL DEFAULT 0,
    active_marker TINYINT GENERATED ALWAYS AS (IF(is_active = 1, 1, NULL)) STORED,
    index_status  VARCHAR(16)  NOT NULL DEFAULT 'idle',
    index_error  TEXT         NULL,
    file_count    INT          NOT NULL DEFAULT 0,
    indexed_at    DATETIME(6)  NULL,
    created_at    DATETIME(6)  NOT NULL,
    updated_at    DATETIME(6)  NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY ux_workspaces_root_path (root_path),
    UNIQUE KEY ux_workspaces_single_active (active_marker)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE sessions (
    id           CHAR(36)     NOT NULL,
    title        VARCHAR(255) NULL,
    workspace_id CHAR(36)     NULL,
    created_at   DATETIME(6)  NOT NULL,
    updated_at   DATETIME(6)  NOT NULL,
    PRIMARY KEY (id),
    KEY ix_sessions_updated (updated_at, id),
    CONSTRAINT fk_sessions_workspace FOREIGN KEY (workspace_id)
        REFERENCES workspaces (id) ON DELETE SET NULL
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;
