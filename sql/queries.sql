SELECT COUNT(*) AS complete_images
FROM images JOIN image_features USING (image_id)
WHERE mask_path IS NOT NULL;

SELECT i.image_id, i.image_path, i.species
FROM images AS i LEFT JOIN image_features AS f USING (image_id)
WHERE f.image_id IS NULL OR i.mask_path IS NULL
ORDER BY i.image_id;

SET @image_id = 1;
SELECT i.image_id, i.image_path, i.mask_path, f.color_feature, f.texture_feature, f.shape_feature
FROM images AS i JOIN image_features AS f USING (image_id)
WHERE i.image_id = @image_id;
