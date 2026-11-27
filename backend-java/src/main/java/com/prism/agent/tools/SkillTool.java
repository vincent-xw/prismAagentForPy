package com.prism.agent.tools;

import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.config.PrismProperties;
import com.prism.agent.core.skills.SkillCatalog;
import com.prism.agent.core.skills.SkillPackage;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;

/** `skill` 只读工具：按需加载技能正文或单个文本资源。 */
@Component
public class SkillTool {

    private static final long MAX_RESOURCE_BYTES = 204_800;
    private static final int MAX_RESOURCES = 50;

    private final SkillCatalog catalog;
    private final PrismProperties properties;

    public SkillTool(SkillCatalog catalog, PrismProperties properties) {
        this.catalog = catalog;
        this.properties = properties;
    }

    public Map<String, Object> invoke(String name, String resourcePath) {
        SkillPackage pkg = catalog.get(name);
        String content;
        List<Map<String, Object>> resources = List.of();
        if (resourcePath != null && !resourcePath.isBlank()) {
            content = readResource(pkg, resourcePath);
        } else {
            content = "<skill_content name=\"" + pkg.name() + "\">\n" + pkg.body() + "\n</skill_content>";
            resources = pkg.resources().stream()
                    .limit(MAX_RESOURCES)
                    .map(item -> Map.<String, Object>of(
                            "path", item.path(), "kind", item.kind(), "bytes", item.bytes()))
                    .toList();
        }
        int max = properties.skillsMaxToolResultChars();
        boolean truncated = content.length() > max;
        Map<String, Object> output = new LinkedHashMap<>();
        output.put("content", truncated ? content.substring(0, max) : content);
        output.put("resources", resources);
        output.put("truncated", truncated);
        return output;
    }

    private String readResource(SkillPackage pkg, String relative) {
        Path base = pkg.directory().toAbsolutePath().normalize();
        Path relativePath = Path.of(relative);
        if (relativePath.isAbsolute() || relativePath.normalize().startsWith("..")) {
            throw new ApiException(
                    ErrorCode.SKILL_PATH_INVALID, "非法资源路径: " + relative, 400, Map.of());
        }
        Path target = base.resolve(relativePath).normalize();
        if (!target.startsWith(base) || !Files.isRegularFile(target)) {
            throw new ApiException(
                    ErrorCode.SKILL_PATH_INVALID, "资源不存在或越界: " + relative, 400, Map.of());
        }
        try {
            if (Files.size(target) > MAX_RESOURCE_BYTES) {
                throw new ApiException(
                        ErrorCode.SKILL_RESOURCE_TOO_LARGE, "资源超过上限: " + relative, 400, Map.of());
            }
            return Files.readString(target, StandardCharsets.UTF_8);
        } catch (IOException error) {
            throw new ApiException(ErrorCode.SKILL_INVALID, "资源不是 UTF-8 文本: " + relative, 400, Map.of());
        }
    }

    public static Map<String, Object> schema() {
        return Map.of(
                "type", "object",
                "properties", Map.of(
                        "name", Map.of("type", "string"),
                        "path", Map.of("type", "string")),
                "required", List.of("name"));
    }
}
