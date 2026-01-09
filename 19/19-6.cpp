#include <iostream>
#include <algorithm>

using namespace std;

int main(){
    int N;
    cin>>N;
    int k = 0;
    for (int temp = N; temp > 1; temp /= 3) {
        k++;
    }

    if (k < 1 || k >= 8) {
        return 0;
    }

    for (int i = 0; i < k; i++) {
        N *= 3; 
    }
 
    cout<<N;
    return 0;
}
