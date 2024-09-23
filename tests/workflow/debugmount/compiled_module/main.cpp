
extern "C" double add(int a, int b);
extern "C" int transform(int a, int b, double *result) {
    *result = add(a,b);
    return 0;
}
