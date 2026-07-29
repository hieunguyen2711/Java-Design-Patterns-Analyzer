abstract class SortAlgorithm {
    public final void sort(int[] data) { if (data.length > 1) { doSort(data); } }
    protected abstract void doSort(int[] data);
}
class QuickSort extends SortAlgorithm {
    protected void doSort(int[] data) { /* partition ... */ }
}
