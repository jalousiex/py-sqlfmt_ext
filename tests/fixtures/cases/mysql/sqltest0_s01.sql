create table if not exists dw.employee (
       id               bigint unsigned    not null auto_increment                            comment '主键',
       name             varchar(64)        not null                 default ''                comment '姓名',
       content          mediumtext                                                                          ,
       data             longblob                                                                            ,
       created_at       datetime           not null                 default current_timestamp               ,
       primary key (id)                                                                                     ,
       key              idx_dept (dept_id)
)
engine = innodb
auto_increment = 1
default charset = utf8mb4
collate = utf8mb4_general_ci
comment = '员工表';
