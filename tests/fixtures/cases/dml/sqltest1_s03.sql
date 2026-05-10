-- 第2段sql
insert overwrite table sch.tab0 partition(*) (
       user_id,
       name   ,
       age
)
with w_tmp as (
select *
  from tbl1
 where 1 = 1
)
select a       ,
       t.c as c,
       t.*
  from DW.mdm.employee_d t --PS
  join (
       select a
         from tab2
        where 1 = 1
       )
    on 1 = 1
 where 1 = 1 --
   and t.a in ('bbb');