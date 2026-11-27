package com.prism.agent.core.skills;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class SkillCatalogTest {

    private Path skill(Path root, String dir, String name, String description, String body) throws Exception {
        Path directory = Files.createDirectories(root.resolve(dir));
        Files.writeString(directory.resolve("SKILL.md"),
                "---\nname: " + name + "\ndescription: " + description + "\n---\n\n" + body);
        return directory;
    }

    @Test
    void parsesSkillAndCollectsResources(@TempDir Path tmp) throws Exception {
        Path root = Files.createDirectories(tmp.resolve("root"));
        Path directory = skill(root, "demo", "demo-skill", "演示", "正文内容");
        Files.createDirectories(directory.resolve("references"));
        Files.writeString(directory.resolve("references").resolve("a.md"), "hello");
        Files.writeString(directory.resolve("ignored.txt"), "ignored");

        SkillCatalog catalog = new SkillCatalog(List.of(root), 8000, 0);

        assertThat(catalog.winners()).extracting(SkillSummary::name).containsExactly("demo-skill");
        SkillPackage pkg = catalog.get("demo-skill");
        assertThat(pkg.body()).isEqualTo("正文内容");
        assertThat(pkg.resources()).extracting(SkillResource::path).containsExactly("references/a.md");
        assertThat(pkg.resources().get(0).kind()).isEqualTo("references");
    }

    @Test
    void sameNameInLaterRootIsShadowed(@TempDir Path tmp) throws Exception {
        Path first = Files.createDirectories(tmp.resolve("first"));
        Path second = Files.createDirectories(tmp.resolve("second"));
        skill(first, "demo", "demo-skill", "先出现", "one");
        skill(second, "demo", "demo-skill", "后出现", "two");

        SkillCatalog catalog = new SkillCatalog(List.of(first, second), 8000, 0);

        List<SkillSummary> all = catalog.list();
        assertThat(all).hasSize(2);
        assertThat(all.get(0).shadowed()).isFalse();
        assertThat(all.get(1).shadowed()).isTrue();
        assertThat(catalog.get("demo-skill").description()).isEqualTo("先出现");
    }

    @Test
    void catalogOverBudgetOmitsEntries(@TempDir Path tmp) throws Exception {
        Path root = Files.createDirectories(tmp.resolve("root"));
        for (int index = 0; index < 40; index++) {
            skill(root, "s" + index, "skill-" + index, "描述".repeat(30), "body");
        }

        SkillCatalog catalog = new SkillCatalog(List.of(root), 800, 0);

        String rendered = catalog.renderCatalog();
        assertThat(rendered.length()).isLessThanOrEqualTo(900);
        assertThat(rendered).contains("已省略");
    }

    @Test
    void invalidNameIsRejected(@TempDir Path tmp) throws Exception {
        Path root = Files.createDirectories(tmp.resolve("root"));
        skill(root, "bad", "Bad_Name", "desc", "body");

        SkillCatalog catalog = new SkillCatalog(List.of(root), 8000, 0);

        assertThat(catalog.list()).isEmpty();
        assertThatThrownBy(() -> Frontmatter.parse("---\nname: Bad_Name\ndescription: d\n---\n"))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).code()).isEqualTo(ErrorCode.SKILL_INVALID));
    }
}
