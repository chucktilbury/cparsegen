cmake_minimum_required(VERSION 3.24)
project(cparsegen LANGUAGES C)

set(CWHIP_BIN_DIR "${PROJECT_SOURCE_DIR}/bin" CACHE PATH
    "Directory for project executables")
set(CWHIP_LIB_DIR "${PROJECT_SOURCE_DIR}/lib" CACHE PATH
    "Directory for project libraries and archives")
set(CVM_PREFIX "" CACHE PATH
    "Prefix containing installed CVM 1.0.0 packages and cvm-run")
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

if(NOT CVM_PREFIX STREQUAL "")
    get_filename_component(CVM_PREFIX "${CVM_PREFIX}" ABSOLUTE)
    set(CVM_MODULE_ROOT "${CVM_PREFIX}/share/cwhip/modules")
    set(CVM_RUNNER "${CVM_PREFIX}/bin/cvm-run")
    set(smallc_cvm_work "${CMAKE_CURRENT_BINARY_DIR}/smallc-cvm")
    set(smallc_cvm_executable "${CWHIP_BIN_DIR}/smallc-cvm")
    set(smallc_cvm_module_overlay "${smallc_cvm_work}/modules")
    foreach(required_file
            "${CVM_MODULE_ROOT}/cvm/1.0.0/cwhip-package.toml"
            "${CVM_MODULE_ROOT}/cvm/1.0.0/cvm.cw"
            "${CVM_MODULE_ROOT}/cvmfile/1.0.0/cwhip-package.toml"
            "${CVM_MODULE_ROOT}/cvmfile/1.0.0/cvmfile.cw"
            "${Cwhip_MODULE_DIR}/system/0.1.0/system.cw"
            "${CVM_RUNNER}")
        if(NOT EXISTS "${required_file}")
            message(FATAL_ERROR
                "CVM_PREFIX does not contain the required installed CVM 1.0.0 "
                "package or runner: ${required_file}")
        endif()
    endforeach()
    set(cvm_test_environment
        "CPARSEGEN_CVM_COMPILER=${smallc_cvm_executable}"
        "CPARSEGEN_CVM_RUNNER=${CVM_RUNNER}")
endif()

add_library(cparsegen_paths OBJECT src/paths.c)
target_include_directories(cparsegen_paths PRIVATE "${Cwhip_INCLUDE_DIR}")
set_target_properties(cparsegen_paths PROPERTIES
    C_STANDARD 99 C_STANDARD_REQUIRED YES C_EXTENSIONS NO)
if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(cparsegen_paths PRIVATE -Wall -Wextra -Werror -pedantic)
endif()
cwhip_add_program(cparsegen
    SOURCE "${PROJECT_SOURCE_DIR}/src/main.cw"
    OBJECTS $<TARGET_OBJECTS:cparsegen_paths>
    DEPENDS cparsegen_paths
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
        ${cvm_test_environment}
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
    set(example_sources
        "${PROJECT_SOURCE_DIR}/examples/${target}/${target}.cw")
    if(target STREQUAL "smallc")
        list(APPEND example_sources
            "${PROJECT_SOURCE_DIR}/examples/smallc/smallc_frontend.cw")
    endif()
    set(example_source_outputs)
    foreach(example_source IN LISTS example_sources)
        get_filename_component(example_source_name "${example_source}" NAME)
        list(APPEND example_source_outputs "${example_work}/${example_source_name}")
    endforeach()
    get_filename_component(cwhip_runtime_directory "${Cwhip_RUNTIME_LIBRARY}" DIRECTORY)
    add_custom_command(
        OUTPUT "${example_executable}"
        COMMAND "${CMAKE_COMMAND}" -E make_directory
            "${example_work}/home" "${example_work}/config"
            "${example_work}/data" "${example_work}/cache"
            "${example_work}/state" "${CWHIP_BIN_DIR}"
        COMMAND "${CMAKE_COMMAND}" -E copy_if_different
            ${example_sources} "${example_work}"
        COMMAND "${cparsegen_executable}" --library
            "${PROJECT_SOURCE_DIR}/examples/${target}/${target}.cpg"
            "${example_work}/parser.cw" --dot "${example_work}/grammar.dot"
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
            ${example_sources}
            "${Cwhip_COMPILER}" "${Cwhip_RUNTIME_LIBRARY}"
        BYPRODUCTS ${example_source_outputs} "${example_work}/parser.cw"
            "${example_work}/${target}.cw" "${example_work}/grammar.dot"
        VERBATIM)
    add_custom_target(${target} DEPENDS "${example_executable}")
endfunction()

cparsegen_add_example(calculator calculator)
cparsegen_add_example(smallc smallc-ast)

if(NOT CVM_PREFIX STREQUAL "")
    get_filename_component(cwhip_runtime_directory "${Cwhip_RUNTIME_LIBRARY}" DIRECTORY)
    add_custom_command(
        OUTPUT "${smallc_cvm_executable}"
        COMMAND "${CMAKE_COMMAND}" -E make_directory
            "${smallc_cvm_work}/home" "${smallc_cvm_work}/config"
            "${smallc_cvm_work}/data" "${smallc_cvm_work}/cache"
            "${smallc_cvm_work}/state" "${smallc_cvm_module_overlay}"
            "${CWHIP_BIN_DIR}"
        COMMAND "${CMAKE_COMMAND}" -E rm -f
            "${smallc_cvm_module_overlay}/cvm"
            "${smallc_cvm_module_overlay}/cvmfile"
            "${smallc_cvm_module_overlay}/system"
        COMMAND "${CMAKE_COMMAND}" -E create_symlink
            "${CVM_MODULE_ROOT}/cvm" "${smallc_cvm_module_overlay}/cvm"
        COMMAND "${CMAKE_COMMAND}" -E create_symlink
            "${CVM_MODULE_ROOT}/cvmfile" "${smallc_cvm_module_overlay}/cvmfile"
        COMMAND "${CMAKE_COMMAND}" -E create_symlink
            "${Cwhip_MODULE_DIR}/system" "${smallc_cvm_module_overlay}/system"
        COMMAND "${cparsegen_executable}" --library
            "${PROJECT_SOURCE_DIR}/examples/smallc/smallc.cpg"
            "${smallc_cvm_work}/parser.cw"
            --dot "${smallc_cvm_work}/grammar.dot"
        COMMAND "${CMAKE_COMMAND}" -E copy_if_different
            "${PROJECT_SOURCE_DIR}/examples/smallc/smallc-cvm.cw"
            "${PROJECT_SOURCE_DIR}/examples/smallc/smallc_frontend.cw"
            "${PROJECT_SOURCE_DIR}/examples/smallc/smallc_backend.cw"
            "${smallc_cvm_work}"
        COMMAND "${CMAKE_COMMAND}" -E env
            --unset=CWHIP_MODULE_DIR --unset=CWHIP_PACKAGE_PATH
            --unset=CWHIP_MODULE_REGISTRY --unset=DESTDIR --unset=XDG_RUNTIME_DIR
            "HOME=${smallc_cvm_work}/home"
            "XDG_CONFIG_HOME=${smallc_cvm_work}/config"
            "XDG_DATA_HOME=${smallc_cvm_work}/data"
            "XDG_CACHE_HOME=${smallc_cvm_work}/cache"
            "XDG_STATE_HOME=${smallc_cvm_work}/state"
            "CWHIP_HOME=${Cwhip_PREFIX}" "CWHIP_INCLUDE_DIR=${Cwhip_INCLUDE_DIR}"
            "CWHIP_RUNTIME_DIR=${cwhip_runtime_directory}"
            "CWHIP_BUILTIN_DIR=${Cwhip_BUILTIN_DIR}"
            "CWHIP_STDLIB_MODULE_DIR=${Cwhip_MODULE_DIR}"
            "CC=${Cwhip_CLANG_EXECUTABLE}"
            "${Cwhip_COMPILER}" "${smallc_cvm_work}/smallc-cvm.cw"
            -M "${smallc_cvm_module_overlay}"
            -o "${smallc_cvm_executable}"
        DEPENDS cparsegen "${cparsegen_executable}"
            "${PROJECT_SOURCE_DIR}/examples/smallc/smallc.cpg"
            "${PROJECT_SOURCE_DIR}/examples/smallc/smallc-cvm.cw"
            "${PROJECT_SOURCE_DIR}/examples/smallc/smallc_frontend.cw"
            "${PROJECT_SOURCE_DIR}/examples/smallc/smallc_backend.cw"
            "${Cwhip_COMPILER}" "${Cwhip_RUNTIME_LIBRARY}"
            "${CVM_MODULE_ROOT}/cvm/1.0.0/cvm.cw"
            "${CVM_MODULE_ROOT}/cvmfile/1.0.0/cvmfile.cw"
            "${Cwhip_MODULE_DIR}/system/0.1.0/system.cw"
        BYPRODUCTS "${smallc_cvm_work}/parser.cw"
            "${smallc_cvm_work}/grammar.dot"
            "${smallc_cvm_work}/smallc-cvm.cw"
            "${smallc_cvm_work}/smallc_frontend.cw"
            "${smallc_cvm_work}/smallc_backend.cw"
        VERBATIM)
    add_custom_target(smallc-cvm DEPENDS "${smallc_cvm_executable}")

    add_custom_target(test-smallc-cvm
        COMMAND "${CMAKE_COMMAND}" -E make_directory
            "${test_work}/home" "${test_work}/config" "${test_work}/data"
            "${test_work}/cache" "${test_work}/state"
        COMMAND "${CMAKE_COMMAND}" -E env
            "HOME=${test_work}/home" "XDG_CONFIG_HOME=${test_work}/config"
            "XDG_DATA_HOME=${test_work}/data" "XDG_CACHE_HOME=${test_work}/cache"
            "XDG_STATE_HOME=${test_work}/state"
            "CPARSEGEN_CVM_COMPILER=${smallc_cvm_executable}"
            "CPARSEGEN_CVM_RUNNER=${CVM_RUNNER}"
            "${Python3_EXECUTABLE}" -m unittest discover
                -s "${PROJECT_SOURCE_DIR}/tests" -p test_smallc_cvm.py -v
        DEPENDS smallc-cvm
        WORKING_DIRECTORY "${PROJECT_SOURCE_DIR}"
        USES_TERMINAL
        VERBATIM)
    add_dependencies(test smallc-cvm)
endif()

function(cparsegen_add_c_example example)
    set(target "${example}-c")
    set(example_work "${CMAKE_CURRENT_BINARY_DIR}/${target}")
    add_custom_command(
        OUTPUT "${example_work}/parser.c"
        COMMAND "${CMAKE_COMMAND}" -E make_directory "${example_work}"
        COMMAND "${cparsegen_executable}" --target c
            "${PROJECT_SOURCE_DIR}/examples/${example}/${example}.cpg"
            "${example_work}/parser.c" --dot "${example_work}/grammar.dot"
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

set(visitor_work "${CMAKE_CURRENT_BINARY_DIR}/visitor-c")
add_custom_command(
    OUTPUT "${visitor_work}/parser.c"
    COMMAND "${CMAKE_COMMAND}" -E make_directory "${visitor_work}"
    COMMAND "${cparsegen_executable}" --target c
        "${PROJECT_SOURCE_DIR}/examples/words.cpg"
        "${visitor_work}/parser.c" --dot "${visitor_work}/grammar.dot"
    DEPENDS cparsegen "${cparsegen_executable}"
        "${PROJECT_SOURCE_DIR}/examples/words.cpg"
    BYPRODUCTS "${visitor_work}/grammar.dot"
    VERBATIM)
add_executable(visitor-c EXCLUDE_FROM_ALL examples/visitor/words.c
    "${visitor_work}/parser.c")
set_source_files_properties("${visitor_work}/parser.c" PROPERTIES HEADER_FILE_ONLY TRUE)
target_include_directories(visitor-c PRIVATE "${visitor_work}")
set_target_properties(visitor-c PROPERTIES
    C_STANDARD 99 C_STANDARD_REQUIRED YES C_EXTENSIONS NO)
if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(visitor-c PRIVATE -Wall -Wextra -Werror -pedantic)
endif()

set(compiler_work "${CMAKE_CURRENT_BINARY_DIR}/expression-compiler")
add_custom_command(
    OUTPUT "${compiler_work}/parser.c"
    COMMAND "${CMAKE_COMMAND}" -E make_directory "${compiler_work}"
    COMMAND "${cparsegen_executable}" --target c
        "${PROJECT_SOURCE_DIR}/examples/compiler/compiler.cpg"
        "${compiler_work}/parser.c" --dot "${compiler_work}/grammar.dot"
    DEPENDS cparsegen "${cparsegen_executable}"
        "${PROJECT_SOURCE_DIR}/examples/compiler/compiler.cpg"
    BYPRODUCTS "${compiler_work}/grammar.dot"
    VERBATIM)
add_executable(expression-compiler EXCLUDE_FROM_ALL examples/compiler/compiler.c
    "${compiler_work}/parser.c")
set_source_files_properties("${compiler_work}/parser.c" PROPERTIES HEADER_FILE_ONLY TRUE)
target_include_directories(expression-compiler PRIVATE "${compiler_work}")
set_target_properties(expression-compiler PROPERTIES
    C_STANDARD 99 C_STANDARD_REQUIRED YES C_EXTENSIONS NO)
if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(expression-compiler PRIVATE -Wall -Wextra -Werror -pedantic)
endif()

set(statement_work "${CMAKE_CURRENT_BINARY_DIR}/statement-compiler")
add_custom_command(
    OUTPUT "${statement_work}/parser.c"
    COMMAND "${CMAKE_COMMAND}" -E make_directory "${statement_work}"
    COMMAND "${cparsegen_executable}" --target c
        "${PROJECT_SOURCE_DIR}/examples/compiler/statements.cpg"
        "${statement_work}/parser.c" --dot "${statement_work}/grammar.dot"
    DEPENDS cparsegen "${cparsegen_executable}"
        "${PROJECT_SOURCE_DIR}/examples/compiler/statements.cpg"
    BYPRODUCTS "${statement_work}/grammar.dot"
    VERBATIM)
add_executable(statement-compiler EXCLUDE_FROM_ALL examples/compiler/statements.c
    "${statement_work}/parser.c")
set_source_files_properties("${statement_work}/parser.c" PROPERTIES HEADER_FILE_ONLY TRUE)
target_include_directories(statement-compiler PRIVATE "${statement_work}")
set_target_properties(statement-compiler PROPERTIES
    C_STANDARD 99 C_STANDARD_REQUIRED YES C_EXTENSIONS NO)
if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(statement-compiler PRIVATE -Wall -Wextra -Werror -pedantic)
endif()
