cmake_minimum_required(VERSION 3.20)
project(antiflood_engine LANGUAGES CXX)
find_package(OpenMP REQUIRED COMPONENTS CXX)
add_library(antiflood_engine SHARED wca2d.cpp)
target_compile_features(antiflood_engine PRIVATE cxx_std_17)
target_link_libraries(antiflood_engine PRIVATE OpenMP::OpenMP_CXX)
set_target_properties(antiflood_engine PROPERTIES
    PREFIX ""
    WINDOWS_EXPORT_ALL_SYMBOLS ON
)
