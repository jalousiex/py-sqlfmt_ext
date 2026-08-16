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