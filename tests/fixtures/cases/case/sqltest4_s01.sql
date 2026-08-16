-- case测试
select -- test
       case -- when SaleOrg1Tag in ('F01') then OrgId1
            -- when SaleOrg2Tag in ('F01')  then OrgId2
            when SaleOrg3Tag in ('F01','ff') then OrgId3
       end                                                                                                 as OrgId_F01,
       case when abc in (1,2)                                               then (case when 2 = 2 --
                                                                                             and 3 = 3 then 3 --
                                                                                       else                 4
                                                                                  end)
            when action is not null                                         then EntryDate -- 22-雇用
            when AccountCodeLv3 in ('A_07', 'A_03') --
                  and (AccountCodeLv4 not in ('EX_040', 'EX_041') --
                       or AccountCodeLv4 in ('EX_024') then '3费用+++++++') then '换行对齐'
            else                                                                 2
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
                        end)       as wc          ,
                       F_USER_CODE as POSTUSERCODE  ,
         from DWS.MSS_CHN_TARGET_CUSTOMER_PRODUCT_CATEGORY_RUIYING_F T1
       ) t1
    on t.a = t1.MONTH
 where t.a in ('bb', 'aaaaaaaaaaaaaaaaaaaa')
   and t.created_at between str_to_date('20241201','%Y%m%d') and days_add(str_to_date('20241201','%Y%m%d'),1);