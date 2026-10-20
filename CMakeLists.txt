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

set(cwhip_sdk_prefix "$ENV{CWHIP_SDK}")
set(cwhip_sdk_selection "CWHIP_SDK")
if(cwhip_sdk_prefix STREQUAL "")
    set(cwhip_config_home "$ENV{XDG_CONFIG_HOME}")
    if(cwhip_config_home STREQUAL "" AND NOT "$ENV{HOME}" STREQUAL "")
        set(cwhip_config_home "$ENV{HOME}/.config")
    endif()
    if(NOT cwhip_config_home STREQUAL "")
        set(cwhip_registration_file_found FALSE)
        if(NOT IS_ABSOLUTE "${cwhip_config_home}")
            message(FATAL_ERROR
                "Cannot discover sdk_prefix: config home '${cwhip_config_home}' is not absolute")
        endif()
        cmake_path(APPEND cwhip_config_home "cwhip"
            OUTPUT_VARIABLE cwhip_settings_directory)
        cmake_path(NORMAL_PATH cwhip_settings_directory)
        set(cwhip_sdk_settings "${cwhip_settings_directory}/sdk.toml")
        set(cwhip_legacy_settings "${cwhip_settings_directory}/settings.toml")
        file(GLOB cwhip_settings_entries
            LIST_DIRECTORIES TRUE "${cwhip_settings_directory}/*")
        if("${cwhip_sdk_settings}" IN_LIST cwhip_settings_entries)
            set(cwhip_registration_file "${cwhip_sdk_settings}")
            set(cwhip_registration_file_found TRUE)
        elseif("${cwhip_legacy_settings}" IN_LIST cwhip_settings_entries)
            set(cwhip_registration_file "${cwhip_legacy_settings}")
            set(cwhip_registration_file_found TRUE)
        endif()
        if(cwhip_registration_file_found)
            find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
            execute_process(
                COMMAND "${Python3_EXECUTABLE}"
                    "${PROJECT_SOURCE_DIR}/scripts/sdk-prefix.py"
                    "${cwhip_registration_file}"
                RESULT_VARIABLE cwhip_settings_result
                OUTPUT_VARIABLE cwhip_sdk_prefix
                ERROR_VARIABLE cwhip_settings_error)
            if(NOT cwhip_settings_result STREQUAL "0")
                message(FATAL_ERROR "${cwhip_settings_error}")
            endif()
            set(cwhip_sdk_selection
                "sdk_prefix in ${cwhip_registration_file}")
        endif()
    endif()
endif()

if(NOT cwhip_sdk_prefix STREQUAL "")
    if(NOT IS_ABSOLUTE "${cwhip_sdk_prefix}" OR
       NOT IS_DIRECTORY "${cwhip_sdk_prefix}")
        message(FATAL_ERROR
            "${cwhip_sdk_selection} selects '${cwhip_sdk_prefix}', which is not "
            "an existing absolute SDK installation prefix. Set CWHIP_SDK to "
            "the complete installed SDK prefix, not its bin/ directory. "
            "See doc/BUILDING.md.")
    endif()
    message(STATUS "Using Cwhip SDK prefix: ${cwhip_sdk_prefix}")
    unset(Cwhip_DIR CACHE)
    unset(Cwhip_DIR)
    find_package(Cwhip 0.0.1 EXACT CONFIG QUIET
        PATHS "${cwhip_sdk_prefix}" NO_DEFAULT_PATH)
else()
    find_package(Cwhip 0.0.1 EXACT CONFIG QUIET)
endif()

if(NOT Cwhip_FOUND)
    if(NOT cwhip_sdk_prefix STREQUAL "")
        set(cwhip_sdk_context
            "${cwhip_sdk_selection} selected '${cwhip_sdk_prefix}'. No fallback SDK was used.")
    else()
        set(cwhip_sdk_context
            "No SDK prefix was selected by CWHIP_SDK or a registered sdk_prefix setting.")
    endif()
    message(FATAL_ERROR
        "Cwhip SDK 0.0.1 was not found or is incompatible. ${cwhip_sdk_context}\n"
        "Select an installed SDK with:\n"
        "  export CWHIP_SDK=\"/absolute/path/to/cwhip-sdk\"\n"
        "  ./scripts/setup\n"
        "Or register top-level sdk_prefix in the selected cwhip/sdk.toml "
        "(legacy settings.toml is used only when sdk.toml is absent), or use "
        "CMAKE_PREFIX_PATH for normal CMake discovery.\n"
        "The SDK normally contains lib/cmake/Cwhip/CwhipConfig.cmake "
        "(CMake also accepts cwhip-config.cmake). Select the whole prefix, "
        "not bin/ or the package directory. If neither config exists, install "
        "the SDK first; cparsegen does not download it. See doc/BUILDING.md.\n"
        "${Cwhip_NOT_FOUND_MESSAGE}")
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

find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
set(test_work "${CMAKE_CURRENT_BINARY_DIR}/tests")
get_filename_component(cwhip_runtime_directory "${Cwhip_RUNTIME_LIBRARY}" DIRECTORY)
add_custom_target(test
    COMMAND "${CMAKE_COMMAND}" -E make_directory
        "${test_work}/home" "${test_work}/config" "${test_work}/data"
        "${test_work}/cache" "${test_work}/state"
    COMMAND "${CMAKE_COMMAND}" -E env
        --unset=CWHIP_MODULE_DIR --unset=CWHIP_PACKAGE_PATH
        --unset=CWHIP_MODULE_REGISTRY --unset=DESTDIR --unset=XDG_RUNTIME_DIR
        "HOME=${test_work}/home" "XDG_CONFIG_HOME=${test_work}/config"
        "XDG_DATA_HOME=${test_work}/data" "XDG_CACHE_HOME=${test_work}/cache"
        "XDG_STATE_HOME=${test_work}/state"
        "CWHIP_SDK=${Cwhip_PREFIX}" "CWHIP_REGISTER_SDK=OFF"
        "CWHIP_HOME=${Cwhip_PREFIX}" "CWHIP_INCLUDE_DIR=${Cwhip_INCLUDE_DIR}"
        "CWHIP_RUNTIME_DIR=${cwhip_runtime_directory}"
        "CWHIP_BUILTIN_DIR=${Cwhip_BUILTIN_DIR}"
        "CWHIP_STDLIB_MODULE_DIR=${Cwhip_MODULE_DIR}"
        "CC=${Cwhip_CLANG_EXECUTABLE}"
        "CPARSEGEN_C_COMPILER=${CMAKE_C_COMPILER}"
        "CPARSEGEN_EXECUTABLE=${cparsegen_executable}"
        "${Python3_EXECUTABLE}" -m unittest discover
            -s "${PROJECT_SOURCE_DIR}/tests" -v
    DEPENDS cparsegen
    WORKING_DIRECTORY "${PROJECT_SOURCE_DIR}"
    USES_TERMINAL
    VERBATIM)

# The SDK application helper currently accepts only non-generated sources.
function(cparsegen_add_example target output_name)
    set(example_work "${CMAKE_CURRENT_BINARY_DIR}/${target}")
    set(example_executable "${CWHIP_BIN_DIR}/${output_name}")
    get_filename_component(cwhip_runtime_directory "${Cwhip_RUNTIME_LIBRARY}" DIRECTORY)
    add_custom_command(
        OUTPUT "${example_executable}"
        COMMAND "${CMAKE_COMMAND}" -E make_directory
            "${example_work}/home" "${example_work}/config"
            "${example_work}/data" "${example_work}/cache"
            "${example_work}/state" "${CWHIP_BIN_DIR}"
        COMMAND "${CMAKE_COMMAND}" -E copy_if_different
            "${PROJECT_SOURCE_DIR}/examples/${target}/${target}.cw"
            "${example_work}/${target}.cw"
        COMMAND "${cparsegen_executable}" --library
            "${PROJECT_SOURCE_DIR}/examples/${target}/${target}.cpg"
            "${example_work}/parser.cw" "${example_work}/grammar.dot"
        COMMAND "${CMAKE_COMMAND}" -E env
            --unset=CWHIP_MODULE_DIR --unset=CWHIP_PACKAGE_PATH
            --unset=CWHIP_MODULE_REGISTRY --unset=DESTDIR --unset=XDG_RUNTIME_DIR
            "HOME=${example_work}/home" "XDG_CONFIG_HOME=${example_work}/config"
            "XDG_DATA_HOME=${example_work}/data" "XDG_CACHE_HOME=${example_work}/cache"
            "XDG_STATE_HOME=${example_work}/state"
            "CWHIP_HOME=${Cwhip_PREFIX}" "CWHIP_INCLUDE_DIR=${Cwhip_INCLUDE_DIR}"
            "CWHIP_RUNTIME_DIR=${cwhip_runtime_directory}"
            "CWHIP_BUILTIN_DIR=${Cwhip_BUILTIN_DIR}"
            "CWHIP_STDLIB_MODULE_DIR=${Cwhip_MODULE_DIR}"
            "CC=${Cwhip_CLANG_EXECUTABLE}"
            "${Cwhip_COMPILER}" "${example_work}/${target}.cw"
            -M "${Cwhip_MODULE_DIR}" -o "${example_executable}"
        DEPENDS cparsegen "${cparsegen_executable}"
            "${PROJECT_SOURCE_DIR}/examples/${target}/${target}.cpg"
            "${PROJECT_SOURCE_DIR}/examples/${target}/${target}.cw"
            "${Cwhip_COMPILER}" "${Cwhip_RUNTIME_LIBRARY}"
        BYPRODUCTS "${example_work}/parser.cw"
            "${example_work}/${target}.cw" "${example_work}/grammar.dot"
        VERBATIM)
    add_custom_target(${target} DEPENDS "${example_executable}")
endfunction()

cparsegen_add_example(calculator calculator)
cparsegen_add_example(smallc smallc-ast)

function(cparsegen_add_c_example example)
    set(target "${example}-c")
    set(example_work "${CMAKE_CURRENT_BINARY_DIR}/${target}")
    add_custom_command(
        OUTPUT "${example_work}/parser.c"
        COMMAND "${CMAKE_COMMAND}" -E make_directory "${example_work}"
        COMMAND "${cparsegen_executable}" --target c
            "${PROJECT_SOURCE_DIR}/examples/${example}/${example}.cpg"
            "${example_work}/parser.c" "${example_work}/grammar.dot"
        DEPENDS cparsegen "${cparsegen_executable}"
            "${PROJECT_SOURCE_DIR}/examples/${example}/${example}.cpg"
        BYPRODUCTS "${example_work}/grammar.dot"
        VERBATIM)
    add_executable(${target} EXCLUDE_FROM_ALL "${example_work}/parser.c")
    set_target_properties(${target} PROPERTIES
        C_STANDARD 99 C_STANDARD_REQUIRED YES C_EXTENSIONS NO)
    if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
        target_compile_options(${target} PRIVATE -Wall -Wextra -Werror -pedantic)
    endif()
endfunction()

cparsegen_add_c_example(calculator)
cparsegen_add_c_example(smallc)
