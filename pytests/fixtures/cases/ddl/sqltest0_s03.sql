-- 视图as
create view if not exists ODS.test_table_rev ( -- 注释
       id                     ,
       id2                    ,
       name     comment '注释',
       descript
) as
select 1          ,
       max(a)     ,
       (1)    as b,
       ''           ;