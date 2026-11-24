#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <omp.h>

namespace {
// Adapt the CADDIES cell/edge calls to a four-neighbour square raster.
// Ghost elevations are only available at exterior boundaries with real DEM coverage.
struct Cell {
    int id;
    const int32_t* adjacent;
    const double* exterior;
    const double* elevation;
    double length;
};

using CA_GRID = Cell;
using CA_REAL = double;
using CA_STATE = unsigned;
using CA_CELLBUFF_REAL_I = const double*;
using CA_CELLBUFF_STATE_I = unsigned;
using CA_EDGEBUFF_REAL_IO = double*;
using CA_GLOB_REAL_I = double;
using CA_ALARMS_O = int;
constexpr int caNeighbours = 4;

#define CA_FUNCTION static void
#define CA_GRID_INIT(grid)
#define CA_ARRAY_CREATE(grid, type, name, size) std::array<type, size> name

unsigned caReadCellBuffState(Cell, unsigned valid, int) { return valid; }
unsigned caReadBitsState(unsigned mask, int, int) { return mask & 1U; }
double caReadCellBuffReal(Cell cell, const double* values, int k) {
    if (k == 0) return values[cell.id];
    const int neighbour = cell.adjacent[k - 1];
    if (neighbour >= 0) return values[neighbour];
    const double edge_height = cell.exterior[k - 1];
    if (std::isfinite(edge_height)) return values == cell.elevation ? edge_height : 0.0;
    return values[cell.id];
}
void caReadCellBuffRealCellArray(Cell cell, const double* values, std::array<double, 5>& result) {
    for (int k = 0; k <= caNeighbours; ++k) {
        result[k] = caReadCellBuffReal(cell, values, k);
    }
}
double caMinReal(double a, double b) { return std::min(a, b); }
double caSqrtReal(double a) { return std::sqrt(a); }
double caLength(Cell cell, int, int) { return cell.length; }
double caArea(Cell cell, int) { return cell.length * cell.length; }
int caUpdateEdges(Cell) { return 4; } // Each donor owns its four outgoing slots.
void caWriteEdgeBuffReal(Cell, double* edges, int k, double flux) { edges[k - 1] = flux; }
int caBoxStatus(Cell) { return 0; } // The adapter supplies valid neighbouring cells and exterior elevations.
void caActivateAlarm(Cell, int, int) {}

#include "vendor/wca2d/outflowWCA2Dv1.ca"
}

extern "C" int wca_selective_step(
    const double* elevation, const double* exterior, double* depth, const double* rain, const double* drain,
    const int32_t* neighbours, const int32_t* valid, int valid_count,
    const int32_t* active, const uint8_t* selected, int count,
    const int32_t* receivers, int receiver_count,
    double length, double dt, double manning, int threads, double* outflow, double* budget,
    uint8_t* received, double* maximum
) {
    double rainfall_depth = 0.0;
    double drained_depth = 0.0;
    double boundary_outflow = 0.0;
    double inactive_inflow = 0.0;
    double deepest = 0.0;
    int team_size = 0;
    if (valid_count > 0) {
        #pragma omp parallel num_threads(threads) reduction(+:rainfall_depth, drained_depth, boundary_outflow, inactive_inflow)
        {
            #pragma omp single
            team_size = omp_get_num_threads();

            #pragma omp for schedule(static)
            for (int index = 0; index < valid_count; ++index) {
                const int id = valid[index];
                if (rain[id] == 0.0 && depth[id] == 0.0) continue;
                const double added = rain[id] * dt;
                const double available = depth[id] + added;
                const double removed = std::min(available, drain[id] * dt);
                depth[id] = available - removed;
                rainfall_depth += added;
                drained_depth += removed;
            }

            #pragma omp for schedule(static)
            for (int index = 0; index < count; ++index) {
                const int id = active[index];
                double* flux = outflow + id * 4;
                std::fill_n(flux, 4, 0.0);
                outflowWCA2Dv1(
                    Cell{id, neighbours + id * 4, exterior + id * 4, elevation, length},
                    flux, elevation, depth,
                    1U, 0, 0.001, 0.0001, dt, 1.0 / manning
                );
            }

            // The same donor volume is subtracted from the donor and added to the receiver.
            // Reading only fluxes (never another cell's depth) makes this update race-free.
            // Only selected cells and their four neighbours can send or receive flow, so the
            // caller passes that set; every other cell has zero net transfer.
            #pragma omp for schedule(static)
            for (int index = 0; index < receiver_count; ++index) {
                const int id = receivers[index];
                const double* outgoing = outflow + id * 4;
                double net = 0.0;
                bool incoming = false;
                for (int k = 0; k < 4; ++k) {
                    const double flux = selected[id] ? outgoing[k] : 0.0;
                    net -= flux;
                    const int neighbour = neighbours[id * 4 + k];
                    if (neighbour < 0) {
                        boundary_outflow += flux;
                    } else if (selected[neighbour]) {
                        const double transfer = outflow[neighbour * 4 + (k + 2) % 4];
                        net += transfer;
                        incoming |= transfer > 0.0;
                    }
                }
                depth[id] += net / (length * length);
                received[id] = !selected[id] && incoming;
                inactive_inflow += received[id];
            }

            // Event maximum and the deepest cell for the next time step, in the same parallel team.
            #pragma omp for schedule(static) reduction(max:deepest)
            for (int index = 0; index < valid_count; ++index) {
                const int id = valid[index];
                if (depth[id] > maximum[id]) maximum[id] = depth[id];
                if (depth[id] > deepest) deepest = depth[id];
            }
        }
    }
    budget[0] = rainfall_depth * length * length;
    budget[1] = drained_depth * length * length;
    budget[2] = boundary_outflow;
    budget[3] = inactive_inflow;  // inactive cells that received inflow; Python reselects tiles then
    budget[4] = deepest;
    return team_size;
}
