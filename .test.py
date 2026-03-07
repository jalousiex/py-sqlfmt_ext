import sys

import sqlfmt

sqltest0 = """
-- DDL测试
create table `schema`.`table` (
       id              INT                                                                           ,
       name            varchar(22)                                                                   ,
       secname         varchar2(22) not null default 0                                               ,
       p_dt            DATETIME              default                   comment '会计期转时间用于分区',
       dw_updated_date DATETIME              default current_timestamp comment 'DW更新时间'
) --
DUPLICATE KEY(id,name) /*默认DUPLICATE KEY()*/
comment '表注释' /*表注释*/
auto partition by range(date_trunc(p_dt, 'month')) () /*range分区键必须非空*/
distributed by hash(ID) buckets auto /*默认RANDOM BUCKETS AUTO*/
properties (
       "dynamic_partition.enable" = "true"                  ,
       "dynamic_partition.prefix" = "p"
);
-- alter table
alter table ODS.test_table_rev add column ( -- 注释2
       id       INT                                                    ,
       id2      datetime     not null default 1312123120               ,
       name     char(20)              default '0'        comment '注释22',
       descript VARCHAR(255) null
);
-- 视图as
create view if not exists ODS.test_table_rev ( -- 注释
       id                     ,
       id2                    ,
       name     comment '注释',
       descript
) as
select 1         ,
       max(a)    ,
       (1)   as b,
       ''        ;
-- 物化视图
create materialized view DM.OA_AS_OPERATION_LOG_UO_F --
refresh auto
    on
commit
partition by(OpDate) as
select *
  from lineitem;
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
   and t.a in (
             'aaaaaaaaaaaaaaaaaaaa',
             'aaaaaaaaaaaaaaaaaaaa'
       );
"""

sqltest1 = """
/*-- DML测试*/
insert into mdm.employee_d_tmp (
       a,
       b,
       c
)
select EmpCode                                                                                            , -- 员工编码,
       curdate() - interval 1 day                                                               HRD_NAME  ,
       curdate() - interval 1 day                                                            as empNAME   ,
       IFNULL(`t3`.`abc`,`t1`.`cde` --
              )                                                                                 ff        ,
       min(StatYM) over(partition by CompanyCode, MaterialCode, KxMaterialCode, RequireType) as StatYM_min, -- 组合最早出现时间
       max(StatYM) over()                                                                    as StatYM_max, -- 整体填报最新时间
       t2.LineManagerPositionName2                                                           as lmpname   ,
       *                                                                                                   -- 直线经理岗位名称
  from DIM.DIM_EMPLOYEE_D as t1 -- mdmvw.vw_employee_base 取自mdm.employee_base 限制RowKey = 1
-- 可改使用DIM.DIM_EMPLOYEE_D 限制RowKey = 1
  left outer join DWD.HR_EMPLOYEE_POST_REL_F as t2 -- mdmvw.vw_employee_post_relation 取自mdm.employee_post_relation 限制RowKey = 1
-- 可改使用DWD.HR_EMPLOYEE_POST_REL_F 限制Rowkey=1，EmpRecordNum=0
    on t1.EmpCode = t2.EmpCode;
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
-- 第3段sql
insert into testdb.test_table (
       user_id,
       name   ,
       age
)
values (1, "Emily", 25)    ,
       (2, "Benjamin", 35) ,
       (3, "Olivia", 28)   ,
       (4, "Alexander", 60),
       (5, "Ava", 17)      ;
"""

sqltest2 = """
-- CTE测试
with tbl1 as(
select a                                                                                                                            , --
       b                                                                                                                            , /*-*/
       c                                                                                                                            , /*-长长长长长长长长长长注释*/
       t.*                                                                                                                          ,
       cast(cast((cast(substring(ComAges, 1, PATINDEX('%年%', ComAges) - 1) as int) * 12 /*-*/
                  + cast(substring(ComAges, PATINDEX('%年%', ComAges) + 1, PATINDEX('%月%', ComAges) - PATINDEX('%年%', ComAges) - 1) as int)) * 1.00 / 12 as decimal(16, 1)) as varchar(10)) as ComAges  ,
       x
  from DW.mdm.employee_d t
 where --
       1 = 1 --
   and 1 = 1
) -- 对齐13
-- 对齐14
select t.EmpName                 ,
       t.EmpRecordNum             /*岗位序号, 0为主岗, 主岗在职是次岗的前提*/,
       t.EffSeq                   /*日期相同时的生效序号, 大的生效*/,
       t.JobCode                 ,
       t.PositionName
  from (
       select *
         from DW.mdm.employee_post_relation_more
       ) t --多岗, 多岗为常态
 where t.EmpRecordNum = 0
-- 顶行首注释
;
create view DWD.HR_EMPLOYEE_INFO_D as --
-- 替代 dwdim.dim_employee_d （改用ODS）
with W_EMPLOYEE_BASE as (
select EMPLID                                                                                                           as EmpCode  ,
       ROW_NUMBER() --
             over(partition by EMPLID order by BGN_DTTM desc, /*-*/
                                               (ifnull(a,0)) asc) rn       ,
  from ODS.PS_HPS_PERS2MDM_VW_001 t1 -- ods.PS_HPS_PERS2MDM_VW_001
 where 1 = 1 --t1.Rowkey=1
--and t1.Rowkey=1
       --and t1.Rowkey=1
) --
, -- 对齐1
W_CTE                as ( --
-- 对齐2
select *
  from W_EMPLOYEE_BASE t1 -- DW.mdm.employee_base
 where t1.RowKey = 1
) -- 对齐3
-- 对齐4
select *
  from W_CTE
"""

sqltest3 = """
-- 嵌套查询测试
 /* 1
 2 3*/
/*-*/
select case t2.ccc2
            when 'a' then 'a2' --
            -- 连续注释对齐
--行首注释固定不动
       end                                                                                                           ,
       H1_HUKOU                                                                                      as CityName       /*-*/
       ,
       (
       select '嵌套' s
         from tab0
        where H1_HUKOU = 0
       )                                                                                             as nest          ,
       ROW_NUMBER() /*-*/
             over(partition by rr order by 1 desc)                                                   as rn            ,
       [location]                                                                                    as NativeCity    , /*-*/
       H2_LOCATION_code                                                                              as NativeCityCode,
       H3_LOCATION_DESCR                                                                             as NativeCityName,
       lead(BGN_DTTM, 1, cast('9999-12-31' as datetime)) over(partition by EMPLID order by BGN_DTTM) as BGN_DTTM_NEXT
  from [ods].[PS_HPS_PERS2MDM_VW_001] t
  join (
       select distinct -- T1.F_MONTH AS "MONTH",
                       T1.F_CUSTOMER_ID as CUSTOMERID,
                       T1.F_OFFICE_NAME as OFFICE    , -- 办事处
                       -- T1.F_CODE AS POSTCODEOUT,
                       T1.F_USER_NAME   as POSTUSER   -- 岗位用户
                       -- T1.F_USER_CODE AS POSTUSERCODE,
         from DWS.MSS_CHN_TARGET_CUSTOMER_PRODUCT_CATEGORY_RUIYING_F T1
       ) t1
    on t.a = t1.MONTH
 where 2 = 2
   and abc in (
       select b
         from tab2
        where 1 = 1
       );
-- 第2段sql
select t.a                                                             ,
       count(iif((t.est_days >= 0 and t.est_days < 7), 1, null)) as cnt,
       t.b                                                             , /*-*/
       t.*
  from DW.ods.tab1 t1
  left outer join (
       select t2.*     ,
              aaa  as a,
         from dw.mdm.tab2 t2
        inner join dw.mdm.tab3 t3
           on t2.oc2 = t3.oc3
        where t2.wc2 = case t2.ccc2
                            when 'a' then 'a2'
                       end
       )tt
    on t1.oc1 = tt.oc/*注释*/
 where 1 = 1
   and t.JobStatusT = 'FilterTxt';
        """

sqltest4 = """
-- case测试
select -- test
       case -- when SaleOrg1Tag in ('F01') then OrgId1
            -- when SaleOrg2Tag in ('F01')  then OrgId2
            when SaleOrg3Tag in ('F01','ff') then OrgId3
       end                                                                                                 as OrgId_F01,
       case when abc in (1,2)                                               then (case when 2 = 2 --
                                                                                             and 3 = 3 then 3 --
                                                                                                       else 4
                                                                                  end)
            when action is not null                                         then EntryDate -- 22-雇用
            when AccountCodeLv3 in ('A_07', 'A_03') --
                  and (AccountCodeLv4 not in ('EX_040', 'EX_041') --
                       or AccountCodeLv4 in ('EX_024') then '3费用+++++++') then '换行对齐'
                                                                            else 2
       end                                                                                                    c        , -- test2
       max(case when action = 'HIR' then EntryDate -- 11-雇用
                when action is not null then EntryDate -- 22-雇用
           end)                                                                                               EntryDate,
       (case t2.ccc2
             when 'a' then 'a2'
        end)                                                                                               as wc       ,
       ROW_NUMBER() --
             over(partition by EMPLID order by BGN_DTTM desc, /*-*/
                                               (case when HPS_E_ADDR_TYPE = '公司' then 1 --
                                                     when HPS_E_ADDR_TYPE = '个人' then 2 else 3 end) asc)    rn       ,
       t.*
  from DW.mdm.employee_d t --PS
  join (
       select distinct (case t2.ccc2
                             when 'a' then 'a2'
                       end) as wc,
                       F_USER_CODE AS POSTUSERCODE,
         from DWS.MSS_CHN_TARGET_CUSTOMER_PRODUCT_CATEGORY_RUIYING_F T1
       ) t1
    on t.a = t1.MONTH
 where t.a in (
             'bb'                  ,
             'aaaaaaaaaaaaaaaaaaaa'
       )
   and t.created_at between str_to_date('20241201','%Y%m%d') and days_add(str_to_date('20241201','%Y%m%d'),1);
create view DWD.HR_EMPLOYEE_LEAVE_HIS_F as
select -- test
       case when HPS_TER_REASON in ('100', '105', '110', '115', '125', '130', '135') then '10'
       end as abc,
       t.*
  from DW.mdm.employee_d t --PS
"""

sqltest5 = """
select EmpCode                                                                  ,
       max(Empname)                                          as Empname         ,
       group_concat(-- 拼接培训详细信息
                    concat('培训时间:', IFNULL(date_format(BeginDate,'yyyy-MM-dd'), 'NULL'), --
                           ',培训类型:', IFNULL(TrainTypeName, 'NULL'), --
                           ',储备级别:', IFNULL(ReserveLevelDescr, 'NULL'), --
                           ',项目名称:', IFNULL(TrainItemName, 'NULL'), --
                           ',培训评价:', IFNULL(cast(TrainEvaluResult as CHAR), 'NULL') --
                           ), '\r\n' order by BeginDate asc) as trainning_detail
  from DWD.HR_EMPLOYEE_TRAINNING_F
 group by EmpCode;
select TJNY                                                                                   as '统计年月',
       DJBH                                                                                   as '单据编号',
       replace(replace(replace(replace(LXYSMC, CHAR(13),''),CHAR(10),''),CHAR(9),''),' ', '') as '客户名称导入',
       DJBH                                                                                   as '单据编号'
  from tab1;
"""

sqltest6 = """
select distinct (1) as wc                    ,
                F_USER_CODE as POSTUSERCODE,
  from DWS.MSS_CHN_TARGET_CUSTOMER_PRODUCT_CATEGORY_RUIYING_F T1;
select a                                                                                                     ,
       1                                                                                    b                ,
       sum(t1.Amount_DFFS) over(partition by t1.AccCompanyCode, --
                                             max(t1.AccDeptCode, --
                                                 ''),t1.VendorCode order by PERIOD desc) as Amount_DFFS_newer,
       (sum(t1.Amount_JFFS --
            - t1.Amount_DFFS))                                                           as Amount_inc       , -- 期间发生额
       (sum(t1.Amount_DQYE - (t1.Amount_JFFS - t1.Amount_DFFS)) --
        - sum(if(t1.PERIOD > t2.PERIOD_ID, t1.Amount_DFFS, 0)))                          as Amount_BegYE     , -- 期初余额=期末余额-(借方发生-贷方发生)
       -- 期初余额=年初余额+借方累计-贷方累计
       c                                                                                 as "aa"             ,
       max(0)                                                                               d
  from tab1
 where 1 = 1
   and 1 = 2
 order by aaaaaa ,
          b1 desc
 limit 10;
select a      ,
       b       /*-*/
       , /*-*/
       b as b1,
       c      ,
       *
  from tab t
 where/*公共条件*/1 = 1
   and (
             '${runtype}' = 'FULL' /*-*/
          or (
                   '${runtype}' = 'INC'
               and 1 = 1 /*增量条件*/
               and (
                   select *
                     from tab2
                    where 1 = 1
                      and 1 = 3 /*增量条件*/
                      and 1 = 2
                   )
             )
       );
"""

sqldebug = """
select 1    ,null,
       level as depth,
       level as depth2   from dual     ;
"""

if __name__ == "__main__":
    if sys.argv[-1] == "-a":
        [exec(f'print("\\n"+"="*15+"sqltest{i}"+"="*15+"\\n"+sqlfmt.sqlfilefmt(sqltest{i}))') for i in range(7)]
    else:
        print("=" * 15 + "\n" + sqlfmt.sqlfilefmt(sqldebug))
