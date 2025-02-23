#include "scenes.h"
#include <stdio.h>
#include <unistd.h>
#include <signal.h>
#include <sys/wait.h>

#define DEFAULT_DOOM_PATH "/usr/games/chocolate-doom"
#define DEFAULT_DOOM_IWAD "/usr/share/games/doom/freedoom1.wad"

// Helper function to check if Doom process is still running
static int is_doom_running(pid_t pid)
{
    if (pid <= 0)
        return 0;

    int status;
    pid_t result = waitpid(pid, &status, WNOHANG);

    if (result == 0)
    {
        // Process is still running
        return 1;
    }
    else if (result == pid)
    {
        // Process has exited
        printf("Doom process exited with status %d\n", WEXITSTATUS(status));
        return 0;
    }
    else
    {
        // Error occurred
        printf("Error checking Doom process status: %d\n", result);
        return 0;
    }
}

void render_doom_scene(SDL_Renderer *renderer, SceneState *state)
{
    // Check if Doom is still running
    if (state->doom_pid > 0 && !is_doom_running(state->doom_pid))
    {
        printf("Doom process %d has terminated\n", state->doom_pid);
        state->doom_pid = 0;
        state->doom_manually_closed = SDL_TRUE; // Mark as manually closed
    }

    // Only start Doom if it's not running AND it wasn't manually closed
    if (state->doom_pid == 0 && !state->doom_manually_closed)
    {
        pid_t pid = fork();
        if (pid == 0)
        {
            // Get MQTT broker from environment variable
            const char *doom_path = getenv("DOOM_PATH");
            if (!doom_path)
            {
                doom_path = DEFAULT_DOOM_PATH;
                printf("DOOM_PATH not set, using default: %s\n", doom_path);
            }
            else
            {
                printf("Using DOOM path: %s\n", doom_path);
            }

            const char *doom_iwad = getenv("DOOM_IWAD");
            if (!doom_iwad)
            {
                doom_iwad = DEFAULT_DOOM_IWAD;
                printf("DOOM_IWAD not set, using default: %s\n", doom_iwad);
            }
            else
            {
                printf("Using DOOM IWAD: %s\n", doom_iwad);
            }

            // Child process
            execl(doom_path, "chocolate-doom", "-window", "-width", "720", "-height", "720", "-iwad", doom_iwad, NULL);
            // If we get here, exec failed
            printf("Failed to start Chocolate Doom\n");
            exit(1);
        }
        else if (pid > 0)
        {
            // Parent process
            state->doom_pid = pid;
            printf("Started Chocolate Doom with PID %d\n", pid);
        }
        else
        {
            printf("Failed to fork process for Chocolate Doom\n");
        }
    }

    // Just render a black screen since Doom runs in its own window
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
    SDL_RenderClear(renderer);
}

// Helper function to cleanup Doom process
void cleanup_doom_process(SceneState *state)
{
    if (state->doom_pid > 0)
    {
        // Check if process is still running first
        if (is_doom_running(state->doom_pid))
        {
            // Try to terminate gracefully first
            kill(state->doom_pid, SIGTERM);

            // Wait a bit for it to terminate
            int status;
            pid_t result = waitpid(state->doom_pid, &status, WNOHANG);

            if (result == 0)
            {
                // If still running after SIGTERM, force kill
                kill(state->doom_pid, SIGKILL);
                waitpid(state->doom_pid, &status, 0);
            }
        }

        state->doom_pid = 0;
        printf("Cleaned up Chocolate Doom process\n");
    }
}