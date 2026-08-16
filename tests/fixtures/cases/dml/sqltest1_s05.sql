select ex.*             ,
       t.ENTERPRISE_NAME,
       t.DW_UPDATED_DATE -- select *
  from DWS.OA_GITHUB_COPILOT_AI_CREDIT_USAGE_F t --
lateral view explode(array('USD', 'RMB')                      ,
                     array(PRICE_PER_UNIT, PRICE_PER_UNIT_CNY),
                     array(GROSS_AMOUNT, GROSS_AMOUNT_CNY)    ) ex as ccy, PRICE_PER_UNIT, GROSS_AMOUNT
 where 1 = 1