-- 查看表中记录总数
SELECT COUNT(*) as total_count FROM face_database;

-- 只保留指定ID的记录，删除其他所有记录
DELETE FROM face_database 
WHERE id NOT IN (106, 107, 108, 109, 110, 111, 117, 118, 120, 121, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145);

-- 执行删除后再次检查记录总数和剩余记录
SELECT COUNT(*) as remaining_count FROM face_database;
SELECT * FROM face_database;