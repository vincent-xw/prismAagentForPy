CREATE TABLE IF NOT EXISTS runs (
    id                    CHAR(36)     NOT NULL,
    session_id            CHAR(36)     NOT NULL,
    workspace_id          CHAR(36)     NULL,
    status                VARCHAR(32)  NOT NULL,
    model_profile_id      CHAR(36)     NULL,
    model_context_window  INT          NULL,
    model_max_output_tokens INT        NULL,
    skill_name            VARCHAR(64)  NULL,
    input_text            MEDIUMTEXT   NOT NULL,
    prompt_name           VARCHAR(128) NOT NULL,
    prompt_version        VARCHAR(64)  NOT NULL,
    system_prompt         MEDIUMTEXT   NOT NULL,
    model                 VARCHAR(128) NOT NULL,
    step_count            INT          NOT NULL DEFAULT 0,
    output_text           MEDIUMTEXT   NULL,
    error_code            VARCHAR(64)  NULL,
    error_message         TEXT         NULL,
    cancel_requested_at   DATETIME(6)  NULL,
    last_event_seq        INT          NOT NULL DEFAULT 0,
    created_at            DATETIME(6)  NOT NULL,
    started_at            DATETIME(6)  NULL,
    finished_at           DATETIME(6)  NULL,
    active_session_id     VARCHAR(36) GENERATED ALWAYS AS (
        CASE WHEN status IN ('queued', 'running', 'waiting_for_tool', 'waiting_for_approval')
             THEN session_id ELSE NULL END) VIRTUAL,
    PRIMARY KEY (id),
    UNIQUE KEY ux_runs_one_active (active_session_id),
    KEY ix_runs_session_created (session_id, created_at),
    KEY ix_runs_status (status),
    CONSTRAINT fk_runs_session FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS messages (
    id           BIGINT       NOT NULL AUTO_INCREMENT,
    session_id   CHAR(36)     NOT NULL,
    run_id       CHAR(36)     NOT NULL,
    role         VARCHAR(16)  NOT NULL,
    kind         VARCHAR(32)  NOT NULL DEFAULT 'text',
    content      JSON         NOT NULL,
    reasoning    TEXT         NULL,
    tool_call_id VARCHAR(128) NULL,
    created_at   DATETIME(6)  NOT NULL,
    PRIMARY KEY (id),
    KEY ix_messages_session (session_id, id),
    UNIQUE KEY ux_messages_run_tool_call (run_id, tool_call_id),
    CONSTRAINT fk_messages_session FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE,
    CONSTRAINT fk_messages_run FOREIGN KEY (run_id) REFERENCES runs (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS tool_calls (
    id                   VARCHAR(128) NOT NULL,
    run_id               CHAR(36)     NOT NULL,
    assistant_message_id BIGINT       NOT NULL,
    tool_name            VARCHAR(128) NOT NULL,
    execution_mode       VARCHAR(16)  NOT NULL,
    status               VARCHAR(16)  NOT NULL,
    input                JSON         NOT NULL,
    output               JSON         NULL,
    input_digest         VARCHAR(80)  NOT NULL,
    error_code           VARCHAR(64)  NULL,
    error_message        TEXT         NULL,
    expires_at           DATETIME(6)  NULL,
    created_at           DATETIME(6)  NOT NULL,
    finished_at          DATETIME(6)  NULL,
    PRIMARY KEY (id),
    KEY ix_tool_calls_run_status (run_id, status),
    CONSTRAINT fk_tool_calls_run FOREIGN KEY (run_id) REFERENCES runs (id) ON DELETE CASCADE,
    CONSTRAINT fk_tool_calls_message FOREIGN KEY (assistant_message_id) REFERENCES messages (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS run_events (
    id         BIGINT      NOT NULL AUTO_INCREMENT,
    run_id     CHAR(36)    NOT NULL,
    seq        INT         NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    payload    JSON        NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY ux_run_events_run_seq (run_id, seq),
    CONSTRAINT fk_run_events_run FOREIGN KEY (run_id) REFERENCES runs (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;
