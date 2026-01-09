#include <iostream>
#include <string>
#include <algorithm>
using namespace std;

int main(){
    string a;
    cin >> a;
    string b = a; 
    reverse(b.begin(), b.end()); 
    
    if (a == b){ 
        cout << "1" << endl;
    } else {
        cout << "0" << endl;
    }
    return 0;
}