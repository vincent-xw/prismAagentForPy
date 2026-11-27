package com.prism.agent.tools;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {"prism.skills-paths=../skills/skills"})
class SkillToolTest {

    @Autowired SkillTool tool;

    @Test
    void loadsBodyWithResources() {
        @SuppressWarnings("unchecked")
        Map<String, Object> result = tool.invoke("prism-demo", null);

        assertThat((String) result.get("content")).contains("<skill_content name=\"prism-demo\">");
        assertThat((Boolean) result.get("truncated")).isFalse();
        assertThat((List<?>) result.get("resources")).anyMatch(item ->
                ((Map<?, ?>) item).get("path").equals("references/checklist.md"));
    }

    @Test
    void readsSingleResource() {
        @SuppressWarnings("unchecked")
        Map<String, Object> result = tool.invoke("prism-demo", "references/checklist.md");

        assertThat((String) result.get("content")).contains("自检清单");
        assertThat((List<?>) result.get("resources")).isEmpty();
    }

    @Test
    void rejectsTraversalAndUnknownSkill() {
        assertThatThrownBy(() -> tool.invoke("prism-demo", "../SKILL.md"))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).code())
                        .isEqualTo(ErrorCode.SKILL_PATH_INVALID));
        assertThatThrownBy(() -> tool.invoke("no-such", null))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).code())
                        .isEqualTo(ErrorCode.SKILL_NOT_FOUND));
    }
}
