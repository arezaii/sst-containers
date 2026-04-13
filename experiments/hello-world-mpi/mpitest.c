#include <mpi.h>
#include <stdio.h>
#include <stdlib.h>

int main (int argc, char **argv) {
        int rc;
        int size;
        int myrank;

        rc = MPI_Init (&argc, &argv);
        if (rc != MPI_SUCCESS) {
                fprintf (stderr, "MPI_Init() failed");
                return EXIT_FAILURE;
        }

        rc = MPI_Comm_size (MPI_COMM_WORLD, &size);
        if (rc != MPI_SUCCESS) {
                fprintf (stderr, "MPI_Comm_size() failed");
                goto exit_with_error;
        }

        rc = MPI_Comm_rank (MPI_COMM_WORLD, &myrank);
        if (rc != MPI_SUCCESS) {
                fprintf (stderr, "MPI_Comm_rank() failed");
                goto exit_with_error;
        }

        // Get the name of the processor (hostname)
        char processor_name[MPI_MAX_PROCESSOR_NAME];
        int name_len;
        rc = MPI_Get_processor_name(processor_name, &name_len);
        if (rc != MPI_SUCCESS) {
                fprintf (stderr, "MPI_Get_processor_name() failed");
                goto exit_with_error;
        }
        fprintf (stdout, "Hello, I am rank %d of %d total ranks\n", myrank, size);

        MPI_Finalize();

        return EXIT_SUCCESS;

 exit_with_error:
        MPI_Finalize();
        return EXIT_FAILURE;
}

/* MPI hello world example */
// #include <stdio.h>
// #include <stdlib.h>
// #include <mpi.h>
// int main(int argc, char **argv) {
//         int rank;
//         MPI_Init(&argc, &argv);
//         MPI_Comm_rank(MPI_COMM_WORLD, &rank);
//         system("whoami");
//         printf("Hello from rank %d\n", rank);
//         MPI_Finalize();
//         return 0;
// }
