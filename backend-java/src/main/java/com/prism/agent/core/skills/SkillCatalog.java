package com.prism.agent.core.skills;

import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** 只读技能目录：多根优先级、同名 shadowed、5 秒缓存与清单渲染。 */
public class SkillCatalog {

    private static final Logger log = LoggerFactory.getLogger(SkillCatalog.class);
    private static final List<String> RESOURCE_KINDS = List.of("references", "scripts", "assets");
    private static final int CLIPPED_DESCRIPTION = 200;

    private final List<Path> roots;
    private final int maxChars;
    private final long cacheMillis;
    private List<SkillSummary> cached;
    private long cachedAt;

    public SkillCatalog(List<Path> roots, int maxChars, double cacheSeconds) {
        this.roots = roots.stream().map(path -> path.toAbsolutePath().normalize()).toList();
        this.maxChars = maxChars;
        this.cacheMillis = (long) (cacheSeconds * 1000);
    }

    public synchronized List<SkillSummary> list() {
        long now = System.currentTimeMillis();
        if (cached != null && now - cachedAt < cacheMillis) {
            return List.copyOf(cached);
        }
        cached = scan();
        cachedAt = now;
        return List.copyOf(cached);
    }

    public List<SkillSummary> winners() {
        return list().stream().filter(item -> !item.shadowed()).toList();
    }

    public SkillPackage get(String name) {
        Optional<SkillSummary> summary =
                winners().stream().filter(item -> item.name().equals(name)).findFirst();
        if (summary.isEmpty()) {
            throw new ApiException(
                    ErrorCode.SKILL_NOT_FOUND, "技能不存在: " + name, 404, Map.of("name", name));
        }
        return load(Path.of(summary.get().path()));
    }

    public String renderCatalog() {
        List<SkillSummary> entries = winners().stream()
                .sorted(Comparator.comparing(SkillSummary::name))
                .toList();
        if (entries.isEmpty()) {
            return "";
        }
        String text = render(entries);
        if (text.length() <= maxChars) {
            return text;
        }
        List<SkillSummary> clipped = entries.stream()
                .map(item -> new SkillSummary(
                        item.name(),
                        item.description().substring(0, Math.min(CLIPPED_DESCRIPTION, item.description().length())),
                        item.path(),
                        item.root(),
                        false))
                .toList();
        text = render(clipped);
        if (text.length() <= maxChars) {
            return text;
        }
        List<SkillSummary> kept = new ArrayList<>(clipped);
        while (!kept.isEmpty() && render(kept).length() > maxChars) {
            kept.remove(kept.size() - 1);
        }
        int omitted = clipped.size() - kept.size();
        return render(kept) + "\n（已省略 " + omitted + " 个技能）";
    }

    private String render(List<SkillSummary> entries) {
        StringBuilder builder = new StringBuilder("<available_skills>\n");
        for (SkillSummary item : entries) {
            builder.append("- ")
                    .append(item.name())
                    .append(": ")
                    .append(item.description())
                    .append(" (path: ")
                    .append(item.path())
                    .append(")\n");
        }
        return builder.append("</available_skills>").toString();
    }

    private List<SkillSummary> scan() {
        List<SkillSummary> summaries = new ArrayList<>();
        Map<String, Boolean> seen = new LinkedHashMap<>();
        for (Path root : roots) {
            if (!Files.isDirectory(root)) {
                continue;
            }
            try (var stream = Files.list(root)) {
                for (Path directory : stream.sorted().toList()) {
                    if (!Files.isDirectory(directory) || !Files.isRegularFile(directory.resolve("SKILL.md"))) {
                        continue;
                    }
                    try {
                        SkillPackage pkg = load(directory);
                        boolean shadowed = seen.containsKey(pkg.name());
                        seen.putIfAbsent(pkg.name(), true);
                        summaries.add(new SkillSummary(
                                pkg.name(),
                                pkg.description(),
                                directory.toAbsolutePath().toString(),
                                root.toString(),
                                shadowed));
                    } catch (RuntimeException error) {
                        log.warn("跳过非法技能目录: {}", directory, error);
                    }
                }
            } catch (IOException error) {
                log.warn("技能目录不可读: {}", root, error);
            }
        }
        return summaries;
    }

    private SkillPackage load(Path directory) {
        if (Files.isSymbolicLink(directory)) {
            throw invalid("技能目录不能是符号链接: " + directory);
        }
        Path skillFile = directory.resolve("SKILL.md");
        if (Files.isSymbolicLink(skillFile)) {
            throw invalid("SKILL.md 不能是符号链接: " + skillFile);
        }
        String text;
        try {
            text = Files.readString(skillFile, StandardCharsets.UTF_8);
        } catch (IOException error) {
            throw invalid("无法读取 " + skillFile);
        }
        Frontmatter.Parsed parsed = Frontmatter.parse(text);
        return new SkillPackage(
                parsed.name(), parsed.description(), parsed.body(), resources(directory), directory);
    }

    private List<SkillResource> resources(Path directory) {
        List<SkillResource> resources = new ArrayList<>();
        for (String kind : RESOURCE_KINDS) {
            Path base = directory.resolve(kind);
            if (!Files.isDirectory(base)) {
                continue;
            }
            try (var stream = Files.walk(base)) {
                stream.filter(Files::isRegularFile).sorted().forEach(path -> {
                    try {
                        resources.add(new SkillResource(
                                directory.relativize(path).toString().replace('\\', '/'),
                                kind,
                                Files.size(path)));
                    } catch (IOException ignored) {
                        // 跳过不可读资源
                    }
                });
            } catch (IOException error) {
                log.warn("资源目录不可读: {}", base, error);
            }
        }
        return resources;
    }

    private ApiException invalid(String message) {
        return new ApiException(ErrorCode.SKILL_INVALID, message, 400, Map.of());
    }
}
