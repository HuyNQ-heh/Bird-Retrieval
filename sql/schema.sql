CREATE TABLE IF NOT EXISTS images (
    image_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    image_path VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL UNIQUE,
    species VARCHAR(255) NOT NULL,
    mask_path VARCHAR(512) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS image_features (
    image_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    color_feature JSON NOT NULL,
    texture_feature JSON NOT NULL,
    shape_feature JSON NOT NULL,
    FOREIGN KEY (image_id) REFERENCES images (image_id),
    CHECK (JSON_SCHEMA_VALID('{"type":"array","items":{"type":"number"},"minItems":640,"maxItems":640}', color_feature)),
    CHECK (JSON_SCHEMA_VALID('{"type":"array","items":{"type":"number"},"minItems":26,"maxItems":26}', texture_feature)),
    CHECK (JSON_SCHEMA_VALID('{"type":"array","items":{"type":"number"},"minItems":12,"maxItems":12}', shape_feature))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
