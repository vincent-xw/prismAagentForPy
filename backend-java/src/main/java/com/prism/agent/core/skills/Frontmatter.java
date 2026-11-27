package com.prism.agent.core.skills;

import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import java.util.Map;
import java.util.regex.Pattern;
import org.yaml.snakeyaml.Yaml;

/** `SKILL.md` frontmatter 切分与校验（与 Python package.py 规则一致）。 */
public final class Frontmatter {

    public static final Pattern NAME = Pattern.compile("^[a-z0-9]+(?:-[a-z0-9]+)*$");
    public static final int MAX_NAME = 64;
    public static final int MAX_DESCRIPTION = 1024;

    private Frontmatter() {
    }

    public record Parsed(String name, String description, String body) {
    }

    @SuppressWarnings("unchecked")
    public static Parsed parse(String text) {
        String[] lines = text.split("\\R", -1);
        if (lines.length == 0 || !"---".equals(lines[0].trim())) {
            throw invalid("SKILL.md 缺少 frontmatter");
        }
        int end = -1;
        for (int index = 1; index < lines.length; index++) {
            if ("---".equals(lines[index].trim())) {
                end = index;
                break;
            }
        }
        if (end < 0) {
            throw invalid("SKILL.md frontmatter 未闭合");
        }
        String frontmatter = String.join("\n", java.util.Arrays.copyOfRange(lines, 1, end));
        String body = String.join("\n", java.util.Arrays.copyOfRange(lines, end + 1, lines.length)).trim();
        Map<String, Object> parsed;
        try {
            Object value = new Yaml().load(frontmatter);
            if (!(value instanceof Map<?, ?> map)) {
                throw invalid("frontmatter 必须是映射");
            }
            parsed = (Map<String, Object>) map;
        } catch (ApiException error) {
            throw error;
        } catch (RuntimeException error) {
            throw invalid("frontmatter 不是合法 YAML");
        }
        String name = String.valueOf(parsed.getOrDefault("name", "")).trim();
        String description = String.valueOf(parsed.getOrDefault("description", "")).trim();
        if (!NAME.matcher(name).matches() || name.length() > MAX_NAME) {
            throw invalid("技能名非法: " + name);
        }
        if (description.isEmpty() || description.length() > MAX_DESCRIPTION) {
            throw invalid("技能 " + name + " 的 description 缺失或过长");
        }
        return new Parsed(name, description, body);
    }

    private static ApiException invalid(String message) {
        return new ApiException(ErrorCode.SKILL_INVALID, message, 400, Map.of());
    }
}
