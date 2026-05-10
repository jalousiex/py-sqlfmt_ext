-- 嵌套查询测试
 /* 1
 2 3*/
/*-*/
select case t2.ccc2
            when 'a' then 'a2' --
-- 连续注释对齐
--行首注释固定不动
       end                                                                                                     ,
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
                       T1.F_USER_NAME   as POSTUSER    -- 岗位用户
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