#include<bits/stdc++.h>
using namespace std;

class Team {
    public:

    string name;
    int id;

    Team() {};
    Team(string n, int id) : name(n), id(id) {}
};

class Match {
    public:

    int team1, team2;
    int matchid;
    string result; // "PENDING", "NR", or winner team name

    Match() {};

    Match(int t1, int t2, int mid, string res) : team1(t1), team2(t2), matchid(mid), result(res) {}
};

int n = 10;
int m = 4;
vector<Team> teams = {
    {"MI",0}, {"CSK",1}, {"RCB",2}, {"KKR",3}, {"RR",4},
    {"DC",5}, {"PBKS",6}, {"SRH",7}, {"GT",8}, {"LSG",9}
};
vector<Match> matches;
vector<vector<int>> h2h;
long long global = 1;
vector<int> points;
vector<pair<int, int>> remainingmatches;
vector<vector<double>> pairwiseprobabilities;
vector<double> probabilities;
const double FORM_WEIGHT = 0.35;
const string PROBABILITY_FILE = "probabilities.txt";

bool IsNumber(const string& s)
{
    if(s.empty())
    {
        return false;
    }
    int i = (s[0] == '-' ? 1 : 0);
    if(i == (int)s.size())
    {
        return false;
    }
    for(; i < (int)s.size(); i++)
    {
        if(!isdigit((unsigned char)s[i]))
        {
            return false;
        }
    }
    return true;
}

string ToUpper(string s)
{
    for(char& ch : s)
    {
        ch = (char)toupper((unsigned char)ch);
    }
    return s;
}

string CurrentTimestamp()
{
    auto now = chrono::system_clock::now();
    time_t nowTime = chrono::system_clock::to_time_t(now);
    tm localTime{};
#ifdef _WIN32
    localtime_s(&localTime, &nowTime);
#else
    localtime_r(&nowTime, &localTime);
#endif
    stringstream ss;
    ss << put_time(&localTime, "%Y-%m-%d %H:%M:%S");
    return ss.str();
}

void WriteProbabilitySnapshot(const string& status)
{
    ofstream fout(PROBABILITY_FILE, ios::trunc);
    if(!fout.is_open())
    {
        cerr << "Failed to open probability file: " << PROBABILITY_FILE << endl;
        return;
    }
    fout << "lastUpdated=" << CurrentTimestamp() << '\n';
    fout << "status=" << status << '\n';
    fout << "remainingMatches=" << remainingmatches.size() << '\n';
    fout << fixed << setprecision(10);
    for(double probability : probabilities)
    {
        fout << probability << '\n';
    }
}

int ParseTeamToken(const string& token, const unordered_map<string, int>& nameToId)
{
    if(IsNumber(token))
    {
        int id = stoi(token);
        if(id >= 0 && id < n) return id;
        return -1;
    }
    auto it = nameToId.find(ToUpper(token));
    if(it == nameToId.end()) return -1;
    return it->second;
}

string ParseResultToken(const string& resultToken, int t1, int t2, const unordered_map<string, int>& nameToId)
{
    if(IsNumber(resultToken))
    {
        int numericResult = stoi(resultToken);
        if(numericResult == -1)
        {
            return "PENDING";
        }
        if(numericResult == 0)
        {
            return "NR";
        }
        if(numericResult == 1)
        {
            return teams[t1].name;
        }
        if(numericResult == 2)
        {
            return teams[t2].name;
        }
        return "__INVALID__";
    }
    string normalized = ToUpper(resultToken);
    if(normalized == "NR" || normalized == "DRAW")
    {
        return "NR";
    }
    if(normalized == "PENDING" || normalized == "NOTPLAYED")
    {
        return "PENDING";
    }
    int winner = ParseTeamToken(resultToken, nameToId);
    if(winner == t1)
    {
        return teams[t1].name;
    }
    if(winner == t2)
    {
        return teams[t2].name;
    }

    return "__INVALID__";
}

bool LoadDataFromFiles(const string& matchesFile, const string& h2hFile)
{
    unordered_map<string, int> nameToId;
    for(const auto& t : teams)
    {
        nameToId[ToUpper(t.name)] = t.id;
    }
    ifstream mfin(matchesFile);
    if(!mfin.is_open())
    {
        cerr << "Failed to open matches file: " << matchesFile << endl;
        return false;
    }
    matches.clear();
    string line;
    int lineNo = 0;
    while(getline(mfin, line))
    {
        lineNo++;
        if(line.empty() || line[0] == '#')
        {
            continue;
        }
        stringstream ss(line);
        string t1Token, t2Token;
        int matchid;
        string resultToken;
        if(!(ss >> t1Token >> t2Token >> matchid >> resultToken))
        {
            cerr << "Invalid matches line " << lineNo << ": " << line << endl;
            return false;
        }
        int t1 = ParseTeamToken(t1Token, nameToId);
        int t2 = ParseTeamToken(t2Token, nameToId);
        if(t1 == -1 || t2 == -1)
        {
            cerr << "Invalid team token in matches line " << lineNo << ": " << line << endl;
            return false;
        }
        string result = ParseResultToken(resultToken, t1, t2, nameToId);
        if(result == "__INVALID__")
        {
            cerr << "Invalid result in matches line " << lineNo << ": " << line << endl;
            cerr << "Use NR, PENDING, or winner team name (" << teams[t1].name << "/" << teams[t2].name << ")" << endl;
            return false;
        }
        matches.push_back({t1, t2, matchid, result});
    }
    ifstream hfin(h2hFile);
    if(!hfin.is_open())
    {
        cerr << "Failed to open h2h file: " << h2hFile << endl;
        return false;
    }
    vector<string> rows;
    while(getline(hfin, line))
    {
        if(line.empty() || line[0] == '#')
        {
            continue;
        }
        rows.push_back(line);
    }
    if((int)rows.size() != n + 1)
    {
        cerr << "Invalid h2h format. Expected header + " << n << " rows." << endl;
        return false;
    }
    vector<string> headerTokens;
    {
        stringstream ss(rows[0]);
        string token;
        while(ss >> token)
        {
            headerTokens.push_back(token);
        }
    }
    if((int)headerTokens.size() != n + 1)
    {
        cerr << "Invalid h2h header. Expected " << n + 1 << " tokens." << endl;
        return false;
    }
    unordered_map<string, int> colTeamToId;
    for(int c=1; c<=n; c++)
    {
        int id = ParseTeamToken(headerTokens[c], nameToId);
        if(id == -1)
        {
            cerr << "Invalid team in h2h header: " << headerTokens[c] << endl;
            return false;
        }
        if(colTeamToId.count(headerTokens[c]))
        {
            cerr << "Duplicate team in h2h header: " << headerTokens[c] << endl;
            return false;
        }
        colTeamToId[headerTokens[c]] = id;
    }

    h2h.assign(n, vector<int>(n, 0));
    vector<bool> seenRow(n, false);
    for(int r=1; r<=n; r++)
    {
        vector<string> rowTokens;
        stringstream ss(rows[r]);
        string token;
        while(ss >> token){
            rowTokens.push_back(token);
        }
        if((int)rowTokens.size() != n + 1)
        {
            cerr << "Invalid h2h row " << r << ". Expected " << n + 1 << " tokens." << endl;
            return false;
        }
        int rowId = ParseTeamToken(rowTokens[0], nameToId);
        if(rowId == -1)
        {
            cerr << "Invalid team in h2h row label: " << rowTokens[0] << endl;
            return false;
        }
        if(seenRow[rowId])
        {
            cerr << "Duplicate h2h row for team: " << rowTokens[0] << endl;
            return false;
        }
        seenRow[rowId] = true;
        for(int c=1; c<=n; c++)
        {
            if(!IsNumber(rowTokens[c]))
            {
                cerr << "Non-integer value in h2h at row " << rowTokens[0] << ", col " << headerTokens[c] << endl;
                return false;
            }
            int colId = ParseTeamToken(headerTokens[c], nameToId);
            h2h[rowId][colId] = stoi(rowTokens[c]);
        }
    }
    for(int i=0; i<n; i++)
    {
        if(!seenRow[i])
        {
            cerr << "Missing h2h row for team: " << teams[i].name << endl;
            return false;
        }
    }
    return true;
}

void PrintPoints()
{
    for(int i=0; i<n; i++)
    {
        cout << teams[i].name  << ": " << points[i] << endl;
    }
}

void PrintMatches()
{
    for(auto& match : matches)
    {
        cout << teams[match.team1].name << " vs " << teams[match.team2].name;
        string normalized = ToUpper(match.result);
        if(normalized == "PENDING")
        {
            cout << " (Not Played)";
        }
        else if(normalized == "NR")
        {
            cout << " (NR)";
        }
        else
        {
            cout << " (" << match.result << " Win)";
        }

        cout << endl;
    }
}

void PrintRemainingMatches()
{
    for(auto& match : remainingmatches)
    {
        cout << teams[match.first].name << " vs " << teams[match.second].name << endl;
    }
}

void PrintPairwiseProbabilities()
{
    cout << "Pairwise Probabilities:" << endl;
    for(int i=0; i<n; i++)
    {
        for(int j=0; j<n; j++)
        {
            if(i != j)
            {
                cout << teams[i].name << " vs " << teams[j].name << ": " << pairwiseprobabilities[i][j] << endl;
            }
        }
    }
}

void PrintProbabilities()
{
    cout << "Probabilities:" << endl;
    for(int i=0; i<n; i++)
    {
        cout << teams[i].name << ": " << probabilities[i] << endl;
    }
}

void InitializePoints()
{
    points.assign(n, 0);
    for(auto& match : matches)
    {
        string normalized = ToUpper(match.result);
        if(normalized == "PENDING")
        {
            continue;
        }
        else if(normalized == "NR")
        {
            points[match.team1]++;
            points[match.team2]++;
        }
        else if(normalized == teams[match.team1].name)
        {
            points[match.team1] += 2;
        }
        else if(normalized == teams[match.team2].name)
        {
            points[match.team2] += 2;
        }
    }
    PrintPoints();
}

void BuildRemainingMatches()
{
    remainingmatches.clear();
    for(auto& match : matches)
    {
        if(ToUpper(match.result) == "PENDING")
        {
            remainingmatches.push_back({match.team1, match.team2});
        }
    }
    PrintRemainingMatches();
}

void BuildPairwiseProbabilities()
{
    pairwiseprobabilities.assign(n, vector<double>(n, 0.0));
    vector<int> played(n, 0);
    for(const auto& match : matches)
    {
        if(ToUpper(match.result) == "PENDING")
        {
            continue;
        }
        played[match.team1]++;
        played[match.team2]++;
    }
    vector<double> form(n, 0.5);
    for(int i=0; i<n; ++i)
    {
        if(played[i] == 0)
        {
            form[i] = 0.5;
        }
        else
        {
            form[i] = (double)points[i] / (played[i] * 2.0);
            if(form[i] < 0.0) form[i] = 0.0;
            if(form[i] > 1.0) form[i] = 1.0;
        }
    }
    for(int i=0; i<n; i++)
    {
        for(int j=0; j<n; j++)
        {
            if(i == j)
            {
                continue;
            }
            double h2hProb = (h2h[i][j] + 1.0) / (h2h[i][j] + h2h[j][i] + 2.0);
            double eps = 1e-9;
            double formProb = (form[i] + eps) / (form[i] + form[j] + 2 * eps);
            pairwiseprobabilities[i][j] = (1.0 - FORM_WEIGHT) * h2hProb + FORM_WEIGHT * formProb;
        }
    }
    PrintPairwiseProbabilities();
}

unordered_map<string, double> memo;

string StateKey(vector<int>& pts)
{
    string key;
    for(int i=0; i<n; i++)
    {
        key += to_string(pts[i]) + ",";
    }
    return key;
}

void Simulate(int idx, vector<int>& pts, double prob)
{
    if(idx == remainingmatches.size())
    {
        memo[StateKey(pts)] += prob;
        return;
    }
    int A = remainingmatches[idx].first;
    int B = remainingmatches[idx].second;
    pts[A] += 2;
    cout << global++ << endl;
    Simulate(idx + 1, pts, prob * pairwiseprobabilities[A][B]);
    pts[A] -= 2;
    pts[B] += 2;
    Simulate(idx + 1, pts, prob * pairwiseprobabilities[B][A]);
    pts[B] -= 2;
}

void ProcessMemo()
{
    for(auto& [key, prob] : memo)
    {
        vector<int> pts;
        stringstream ss(key);
        string token;
        while(getline(ss, token, ','))
        {
            pts.push_back(stoi(token));
        }
        vector<pair<int,int>> v;
        for(int i=0; i<n; i++)
        {
            v.push_back({pts[i], i});
        }
        sort(v.begin(), v.end(), greater<>());
        int i = 0, taken = 0;
        while(i < n && taken < min(m, n))
        {
            int j = i;
            while(j < n && v[j].first == v[i].first)
            {
                j++;
            }
            int groupSize = j - i;
            int slots = min(m, n) - taken;
            int use = min(groupSize, slots);
            double share = (double)use / groupSize;
            for(int k = i; k < j; k++)
            {
                probabilities[v[k].second] += prob * share;
            }
            taken += use;
            i = j;
        }
    }
}

void SimulateMatches()
{
    probabilities.assign(n, 0.0);
    memo.clear();
    vector<int> pts = points;
    Simulate(0, pts, 1.0);
    ProcessMemo();
    PrintProbabilities();
}

int main()
{
    auto time_start = chrono::steady_clock::now();
    if(!LoadDataFromFiles("matches.txt", "h2h.txt"))
    {
        cerr << "Input format:" << endl;
        cerr << "matches.txt -> <team1> <team2> <matchid> <result> (result: NR, PENDING, or winner team name)" << endl;
        cerr << "h2h.txt -> first row header + row labels, example: TEAM MI CSK ... then MI 0 21 ..." << endl;
        auto time_end = chrono::steady_clock::now();
        auto elapsed_ms = chrono::duration_cast<chrono::milliseconds>(time_end - time_start).count();
        cout << "Time taken: " << elapsed_ms << " ms" << endl;
        return 1;
    }
    cout << "-------" << endl;
    PrintMatches();
    cout << "-------" << endl;
    InitializePoints();
    cout << "-------" << endl;
    BuildRemainingMatches();
    cout << "-------" << endl;
    BuildPairwiseProbabilities();
    cout << "-------" << endl;
    SimulateMatches();
    cout << "-------" << endl;
    WriteProbabilitySnapshot("computed");
    auto time_end = chrono::steady_clock::now();
    auto elapsed_ms = chrono::duration_cast<chrono::milliseconds>(time_end - time_start).count();
    cout << "Time taken: " << elapsed_ms << " ms" << endl;
}