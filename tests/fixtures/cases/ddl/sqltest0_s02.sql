-- alter table
alter table ODS.test_table_rev add column ( -- 注释2
       id       INT                                                      ,
       id2      datetime     not null default 1312123120                 ,
       name     char(20)              default '0'        comment '注释22',
       descript VARCHAR(255) null
);