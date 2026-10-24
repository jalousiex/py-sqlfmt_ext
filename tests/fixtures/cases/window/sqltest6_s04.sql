select *                                                                                   ,
       greatest(least(Amount_JFFS, Amount_endYE), 0)                 as Amount_assign      , -- 分配的应收，循环增量
       sum(greatest(least(Amount_JFFS, Amount_endYE), 0)) --
             over(partition by AccCompanyCode, AccDeptCode, VendorCode, --
                               Account_type order by PERIOD_ID desc) as Amount_assign_after, -- 当月及之后月累计增量
       first_value(Amount_DQYE) --
             over(partition by AccCompanyCode, AccDeptCode, VendorCode, --
                               Account_type order by PERIOD_ID desc) as Amount_DQYE_first  , -- 基准月原始期末余额
       first_value(Amount_endYE) --
             over(partition by AccCompanyCode, AccDeptCode, VendorCode, --
                               Account_type order by PERIOD_ID desc) as Amount_endYE_first   -- 基准月应收
  from W_FIN_AR_ACCOUNT_PERIOD_TMP1 t1
