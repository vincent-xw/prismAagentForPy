package com.prism.agent.application.mcp;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;

/** 逐字复刻 Python naming.py：mcp__<slug>__<tool>，超 64 字符追加 6 位哈希。 */
public final class McpToolNaming {

    private static final int MAX_TOOL_NAME = 64;

    private McpToolNaming() {
    }

    public static String slugify(String name) {
        String slug = name == null ? "" : name.trim().toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9_-]+", "-");
        slug = slug.replaceAll("^[-_]+", "").replaceAll("[-_]+$", "");
        return slug.isEmpty() ? "server" : slug;
    }

    public static String fullName(String serverName, String toolName) {
        String prefix = "mcp__" + slugify(serverName) + "__";
        String safe = toolName == null ? "" : toolName.replaceAll("[^A-Za-z0-9_-]", "_");
        String full = prefix + safe;
        if (full.length() <= MAX_TOOL_NAME) {
            return full;
        }
        String digest = sha256(full).substring(0, 6);
        int keep = MAX_TOOL_NAME - prefix.length() - "__".length() - digest.length();
        return prefix + safe.substring(0, Math.max(0, Math.min(keep, safe.length()))) + "__" + digest;
    }

    private static String sha256(String value) {
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder builder = new StringBuilder();
            for (byte item : hash) {
                builder.append(String.format("%02x", item));
            }
            return builder.toString();
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }
}
