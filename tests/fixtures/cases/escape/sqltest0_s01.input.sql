select concat(a, '\\', b) as joined, c like 'ex%' from t where d = 'x\\y'
