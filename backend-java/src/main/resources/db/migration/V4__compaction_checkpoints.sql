CREATE TABLE IF NOT EXISTS compaction_checkpoints (
    id                    CHAR(36)  NOT NULL,
    session_id            CHAR(36)  NOT NULL,
    run_id                CHAR(36)  NULL,
    summary               MEDIUMTEXT NOT NULL,
    first_kept_message_id CHAR(36)  NOT NULL,
    tokens_before         INT       NOT NULL,
    tokens_after          INT       NOT NULL,
    created_at            DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    KEY ix_compaction_session_created (session_id, created_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;
