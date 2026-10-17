cmake_minimum_required(VERSION 3.24)
project(cparsegen LANGUAGES C)

set(CWHIP_BIN_DIR "${PROJECT_SOURCE_DIR}/bin" CACHE PATH
    "Directory for project executables")
set(CWHIP_LIB_DIR "${PROJECT_SOURCE_DIR}/lib" CACHE PATH
    "Directory for project libraries and archives")
get_filename_component(CWHIP_BIN_DIR "${CWHIP_BIN_DIR}" ABSOLUTE
    BASE_DIR "${PROJECT_SOURCE_DIR}")
get_filename_component(CWHIP_LIB_DIR "${CWHIP_LIB_DIR}" ABSOLUTE
    BASE_DIR "${PROJECT_SOURCE_DIR}")

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CWHIP_BIN_DIR}")
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY "${CWHIP_LIB_DIR}")
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY "${CWHIP_LIB_DIR}")
foreach(configuration DEBUG RELEASE RELWITHDEBINFO MINSIZEREL)
    set(CMAKE_RUNTIME_OUTPUT_DIRECTORY_${configuration} "${CWHIP_BIN_DIR}")
    set(CMAKE_LIBRARY_OUTPUT_DIRECTORY_${configuration} "${CWHIP_LIB_DIR}")
    set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY_${configuration} "${CWHIP_LIB_DIR}")
endforeach()

if(DEFINED ENV{CWHIP_SDK} AND NOT "$ENV{CWHIP_SDK}" STREQUAL "")
    unset(Cwhip_DIR CACHE)
    unset(Cwhip_DIR)
    find_package(Cwhip 0.0.1 EXACT CONFIG REQUIRED
        PATHS "$ENV{CWHIP_SDK}" NO_DEFAULT_PATH)
else()
    find_package(Cwhip 0.0.1 EXACT CONFIG REQUIRED)
endif()

if(NOT Cwhip_APPLICATION_OUTPUT_DIRECTORIES)
    message(FATAL_ERROR
        "The selected Cwhip SDK does not support configurable application output directories. "
        "Install an SDK that provides Cwhip_APPLICATION_OUTPUT_DIRECTORIES.")
endif()

cwhip_add_program(cparsegen
    SOURCE "${PROJECT_SOURCE_DIR}/src/main.cw"
    OUTPUT_DIRECTORY "${CWHIP_BIN_DIR}")
get_target_property(cparsegen_executable cparsegen CWHIP_EXECUTABLE)
install(PROGRAMS "${cparsegen_executable}" DESTINATION bin)
