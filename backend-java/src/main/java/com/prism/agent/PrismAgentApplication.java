package com.prism.agent;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class PrismAgentApplication {

    public static void main(String[] args) {
        SpringApplication.run(PrismAgentApplication.class, args);
    }
}
