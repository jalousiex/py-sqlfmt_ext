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