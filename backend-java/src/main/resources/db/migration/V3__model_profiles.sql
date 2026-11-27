CREATE TABLE IF NOT EXISTS model_profiles (
    id                CHAR(36)     NOT NULL,
    name              VARCHAR(128) NOT NULL,
    base_url          TEXT         NOT NULL,
    model             VARCHAR(128) NOT NULL,
    api_key_env       VARCHAR(128) NOT NULL,
    api_key           TEXT         NULL,
    context_window    INT          NOT NULL,
    max_output_tokens INT          NOT NULL,
    is_active         TINYINT(1)   NOT NULL DEFAULT 0,
    active_marker     TINYINT GENERATED ALWAYS AS (IF(is_active = 1, 1, NULL)) VIRTUAL,
    created_at        DATETIME(6)  NOT NULL,
    updated_at        DATETIME(6)  NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY ux_model_profiles_name (name),
    UNIQUE KEY ux_model_profiles_one_active (active_marker)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;
