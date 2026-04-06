GRANT SELECT, INSERT, UPDATE, DELETE
    ON `heritage_ops`.* TO 'heritage'@'%';
GRANT ALL PRIVILEGES
    ON `test_heritage_ops`.* TO 'heritage'@'%';
FLUSH PRIVILEGES;
