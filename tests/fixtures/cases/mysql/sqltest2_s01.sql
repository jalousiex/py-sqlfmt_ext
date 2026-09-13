select straight_join a.id  ,
                     a.name
  from t1 a
straight_join t2 b
    on a.id = b.aid
 where a.st = 1;
