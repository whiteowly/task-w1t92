FROM mysql:8.4

COPY docker/mysql/entrypoint.sh /usr/local/bin/heritage-mysql-entrypoint.sh
COPY docker/mysql/init/001_local_dev_grants.sql /docker-entrypoint-initdb.d/001_local_dev_grants.sql
RUN chmod +x /usr/local/bin/heritage-mysql-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/heritage-mysql-entrypoint.sh"]
CMD ["mysqld"]
