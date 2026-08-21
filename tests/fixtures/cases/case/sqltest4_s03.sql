select a               ,
       case
            when b in ('X', 'Y') then b || '(' || c || ')'
            when b = 'NUMBER'    then b || '(' || nvl(c, '38') || ',' || nvl(d, '0') || ')'
            else                      c
       end as type_name
  from t