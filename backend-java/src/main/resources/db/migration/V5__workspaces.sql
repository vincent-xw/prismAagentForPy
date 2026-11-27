-- V1 已创建最小 workspaces 表；这里补齐命名与权限档位列。
ALTER TABLE workspaces
    ADD COLUMN name VARCHAR(128) NULL AFTER label,
    ADD COLUMN user VARCHAR(128) NULL AFTER name,
    ADD COLUMN permission_mode VARCHAR(16) NOT NULL DEFAULT 'workspace_write' AFTER user;
