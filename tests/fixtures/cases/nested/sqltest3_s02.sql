-- 第2段sql
select t.a                                                             ,
       count(iif((t.est_days >= 0 and t.est_days < 7), 1, null)) as cnt,
       t.b                                                             , /*-*/
       t.*
  from DW.ods.tab1 t1
  left outer join (
       select t2.*     ,
              aaa  as a  ,
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