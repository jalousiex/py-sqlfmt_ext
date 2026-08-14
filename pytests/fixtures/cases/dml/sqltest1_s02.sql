-- 第1段sql
insert into `sch`.tab0 (
       user_id,
       name   ,
       age
)
with w_tmp as (
select *
  from tbl1
 where 1 = 1
)
select a                                                       ,
       IFNULL(`t3`.`AD_HRD_NAME`,`t1`.`HRD_NAME`) as `HRD_NAME`,
       b                                                       , /*-*/
       c                                                       ,
       t.*
  from DW.mdm.employee_d t --PS
  join (
       select a
         from tab2
        where 1 = 1 --
        group by a
       ) --com
-- 连续注释
    on 1 = 1
  join tab2.longlonglongtabname --com2
-- 连续注释2
    on 1 = 1
 where (
             1 = 1 --
         and t.a = '0'
       )
   and t.a in ('aaaaaaaaaaaaaaaaaaaa');