-- 表as
create table tab0 as
with w_tmp as (
select *
  from tbl1
 where 1 = 1 --
)
select min(1)                                        a         ,
       min(a)                                                  ,
       max(b)                                     as bb        , -- 单行注释
       -- 连续注释
       max(StatYM) over()                         as StatYM_max, -- 整体填报最新时间
       IFNULL(`t3`.`AD_HRD_NAME`,`t1`.`HRD_NAME`) as `HRD_NAME`,
       b                                                       , /*-*/
       c                                                       ,
       t.*
  from DW.mdm.employee_d t --PS
  join (
       select a
         from tab2
        where 1 = 1
       )
    on 1 = 1
 where 1 = 1 --
-- 行首注释
   and t.a in ('aaaaaaaaaaaaaaaaaaaa', 'aaaaaaaaaaaaaaaaaaaa');