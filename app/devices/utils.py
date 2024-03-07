def array2str(arr, digits=2):
    return ", ".join([f"{x:.{digits}f}" for x in arr])
