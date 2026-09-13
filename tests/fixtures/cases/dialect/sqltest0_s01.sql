create table if not exists dw.mdm.employee_d (
       id          int        ,
       name        varchar(10),
       create_time datetime
)
duplicate key(id)
distributed by hash(id) buckets 16
properties ('replication_num' = '3');
