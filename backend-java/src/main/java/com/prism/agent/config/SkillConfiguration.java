package com.prism.agent.config;

import com.prism.agent.core.skills.SkillCatalog;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SkillConfiguration {

    @Bean
    public SkillCatalog skillCatalog(PrismProperties properties) {
        List<Path> roots = new ArrayList<>();
        roots.add(expand(properties.prismHome()).resolve("skills"));
        roots.add(Path.of(System.getProperty("user.home")).resolve(".agent/skills"));
        roots.add(Path.of(System.getProperty("user.home")).resolve(".agents/skills"));
        for (String part : properties.skillsPaths().split(",")) {
            if (!part.isBlank()) {
                roots.add(expand(part.trim()));
            }
        }
        return new SkillCatalog(roots, properties.skillsCatalogMaxChars(), 5.0);
    }

    private Path expand(String raw) {
        if (raw.startsWith("~")) {
            return Path.of(System.getProperty("user.home") + raw.substring(1)).toAbsolutePath().normalize();
        }
        return Path.of(raw).toAbsolutePath().normalize();
    }
}
