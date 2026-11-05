#include "../ai_tools/AiServiceHealth.h"
#include <cassert>

using namespace test;

int main() {
    auto first = getAiServiceHealth("ipc:///tmp/test_ai_health.ipc");
    auto second = getAiServiceHealth("ipc:///tmp/test_ai_health.ipc");
    auto other = getAiServiceHealth("ipc:///tmp/test_ai_health_other.ipc");

    assert(first == second);
    assert(first != other);
    assert(!first->isOnline());
    assert(first->tryAcquireProbe());
    assert(!second->tryAcquireProbe());

    auto online = first->reportOnline();
    assert(online.changed);
    assert(first->isOnline());
    assert(!first->tryAcquireProbe());

    auto offline = second->reportOffline();
    assert(offline.changed);
    assert(offline.retryDelaySeconds == 1);
    assert(!first->isOnline());
    assert(!first->tryAcquireProbe());
    return 0;
}
