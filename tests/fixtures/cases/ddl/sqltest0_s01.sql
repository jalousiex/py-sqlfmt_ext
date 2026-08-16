-- DDL测试
create table `schema`.`table` (
       id              INT                                                                           ,
       name            varchar(22)                                                                   ,
       secname         varchar2(22) not null default 0                                               ,
       p_dt            DATETIME              default                   comment '会计期转时间用于分区',
       dw_updated_date DATETIME              default current_timestamp comment 'DW更新时间'
) --
duplicate key(id,name) /*默认DUPLICATE KEY()*/
comment '表注释' /*表注释*/
auto partition by range(date_trunc(p_dt, 'month')) () /*range分区键必须非空*/
distributed by hash(ID) buckets auto /*默认RANDOM BUCKETS AUTO*/
properties (
       "dynamic_partition.enable" = "true",
       "dynamic_partition.prefix" = "p"
);