package com.prism.agent.tools;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.Workspace;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class WorkspaceToolExecutorTest {

    private final WorkspaceToolExecutor executor = new WorkspaceToolExecutor();

    private Workspace workspace(Path root, String mode) {
        Instant now = Instant.now();
        return new Workspace("w1", root.toString(), "l", null, null, mode, true, "idle", null, 0, null, now, now);
    }

    @Test
    void readOnlyBlocksWriteAndDelete(@TempDir Path root) throws Exception {
        Path file = root.resolve("a.txt");
        Files.writeString(file, "x");

        assertThatThrownBy(() -> executor.execute(
                        "file_write", Map.of("path", "b.txt", "content", "y"), workspace(root, "read_only")))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).code())
                        .isEqualTo(ErrorCode.WORKSPACE_READ_ONLY));

        assertThatThrownBy(() -> executor.execute(
                        "file_delete", Map.of("path", "a.txt"), workspace(root, "read_only")))
                .isInstanceOf(ApiException.class);
        assertThat(Files.exists(file)).isTrue();
    }

    @Test
    void workspaceWriteBlocksEscapeButAllowsInnerWrites(@TempDir Path root) throws Exception {
        assertThatThrownBy(() -> executor.execute(
                        "file_read", Map.of("path", "../../etc/passwd"), workspace(root, "workspace_write")))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).code())
                        .isEqualTo(ErrorCode.WORKSPACE_PATH_OUTSIDE));

        executor.execute(
                "file_write", Map.of("path", "dir/a.txt", "content", "hello", "mode", "create"),
                workspace(root, "workspace_write"));
        var read = executor.execute("file_read", Map.of("path", "dir/a.txt"), workspace(root, "workspace_write"));
        assertThat(read.get("content")).isEqualTo("hello");
    }

    @Test
    void deleteRejectsNonEmptyDirAndAllowsEmpty(@TempDir Path root) throws Exception {
        executor.execute(
                "file_write", Map.of("path", "dir/a.txt", "content", "x"), workspace(root, "workspace_write"));

        assertThatThrownBy(() -> executor.execute(
                        "file_delete", Map.of("path", "dir"), workspace(root, "workspace_write")))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).code())
                        .isEqualTo(ErrorCode.WORKSPACE_DIR_NOT_EMPTY));

        executor.execute("file_delete", Map.of("path", "dir/a.txt"), workspace(root, "workspace_write"));
        executor.execute("file_delete", Map.of("path", "dir"), workspace(root, "workspace_write"));
        assertThat(Files.exists(root.resolve("dir"))).isFalse();
    }

    @Test
    void fullAccessAllowsOutsidePath(@TempDir Path root) throws Exception {
        Path workspaceDir = Files.createDirectory(root.resolve("ws"));
        Path outside = Files.writeString(root.resolve("outside.txt"), "out");

        var read = executor.execute("file_read", Map.of("path", outside.toString()), workspace(workspaceDir, "full_access"));

        assertThat(read.get("content")).isEqualTo("out");
    }

    @Test
    void modeChangeTakesEffectImmediately(@TempDir Path root) throws Exception {
        executor.execute("file_write", Map.of("path", "a.txt", "content", "1"), workspace(root, "workspace_write"));

        assertThatThrownBy(() -> executor.execute(
                        "file_write", Map.of("path", "a.txt", "content", "2"), workspace(root, "read_only")))
                .isInstanceOf(ApiException.class);
        assertThat(Files.readString(root.resolve("a.txt"))).isEqualTo("1");
    }
}
