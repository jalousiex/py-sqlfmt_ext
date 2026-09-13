insert into t (
       a,
       b
)
values (1, 2)
on duplicate key update b = values(b);
