import pygame
import json
import os
from datetime import datetime
import sqlite3

# Define the root directory
ROOT_DIR = os.path.dirname(__file__)  # Automatically gets the script's directory
LEVEL_PATH = os.path.join(ROOT_DIR, 'level.json')  # Relative path to the file
# === Constants === #
WINDOW_WIDTH, WINDOW_HEIGHT = 800, 600  # Viewport dimensions
WORLD_WIDTH, WORLD_HEIGHT = 4069, 2048  # World dimensions
SKYBOX_HEIGHT = 50  # Player cannot exceed this height vertically
# Colors
COLORS = {
    "player": (255, 0, 0),  # Red player
    "platform": (0, 255, 0),  # Green platforms
    "background": (0, 0, 0),  # Black background
    "border": (255, 255, 0),  # Bright yellow borders
}

# Player stats
PLAYER_STATS = {
    "size": 15,  # Player dimensions
    "start_pos": [200, 200],  # Starting position
    "speed": 3.5,  # Normal movement speed
    "dash_speed": 9,  # Dash movement speed
    "dash_cooldown": 500,  # Dash cooldown time in milliseconds
    "jump_force": -5,  # Jump force (upward velocity)
}

GRAVITY = 0.2
MAX_FALL_SPEED = 10
BORDER_THICKNESS = 5  # Thickness of the borders

# === Classes === #
class Platform:
    """Represents a platform in the game."""
    def __init__(self, x, y, width, height):
        self.rect = pygame.Rect(x, y, width, height)

class Camera:
    """A simple camera to follow the player within the world boundaries."""
    def __init__(self, world_width, world_height):
        self.camera = pygame.Rect(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT)  # Viewport size
        self.world_width = world_width
        self.world_height = world_height

    def apply(self, rect):
        """Offset a rectangle's position by the camera's position."""
        return rect.move(-self.camera.topleft[0], -self.camera.topleft[1])

    def update(self, target):
        """Center the camera on the target (e.g., the player) while clamping to world borders."""
        x = max(0, min(target.centerx - WINDOW_WIDTH // 2, self.world_width - WINDOW_WIDTH))
        y = max(0, min(target.centery - WINDOW_HEIGHT // 2, self.world_height - WINDOW_HEIGHT))
        self.camera = pygame.Rect(x, y, WINDOW_WIDTH, WINDOW_HEIGHT)
    
class Coin:
    """Represents a collectible coin in the game."""
    def __init__(self, x, y, size=10):
        self.rect = pygame.Rect(x, y, size, size)
        self.collected = False  # Tracks if the coin has been collected

class DamageBrick:
    """Represents a brick that damages the player on contact."""
    def __init__(self, x, y, width=50, height=50, damage=25):
        self.rect = pygame.Rect(x, y, width, height)
        self.damage = damage


# === Functions === #
def apply_physics(player):
    """Applies gravity and updates the player's position."""
    if not player["is_dashing"]:  # Gravity only applies when not dashing
        if not player["is_grounded"]:
            player["y_velocity"] += GRAVITY  # Apply gravity
            player["y_velocity"] = min(player["y_velocity"], MAX_FALL_SPEED)  # Cap falling speed
    else:
        player["dash_timer"] -= 1  # Count down the dash timer
        if player["dash_timer"] <= 0:  # Dash ends
            player["is_dashing"] = False
            player["x_velocity"] = 0  # Reset horizontal velocity after dashing

    player["pos"][1] += player["y_velocity"]  # Update vertical position

def constrain_player_to_world(player):
    """Ensures the player stays within world boundaries (including skybox)."""
    # Horizontal boundaries (left and right edges)
    if player["pos"][0] < 0:
        player["pos"][0] = 0
        player["x_velocity"] = 0
    elif player["pos"][0] > WORLD_WIDTH - PLAYER_STATS["size"]:
        player["pos"][0] = WORLD_WIDTH - PLAYER_STATS["size"]
        player["x_velocity"] = 0

    # Vertical boundaries (floor and skybox)
    if player["pos"][1] < SKYBOX_HEIGHT:  # Skybox constraint
        player["pos"][1] = SKYBOX_HEIGHT
        player["y_velocity"] = 0  # Stop upward movement
    elif player["pos"][1] > WORLD_HEIGHT - PLAYER_STATS["size"]:  # Floor constraint
        player["pos"][1] = WORLD_HEIGHT - PLAYER_STATS["size"]
        player["y_velocity"] = 0  # Stop falling
        player["is_grounded"] = True  # Consider player grounded on the floor

def move_player(player, keys, delta_time):
    """Moves the player based on input."""
    if player["is_dashing"]:  # Ignore normal movement while dashing
        player["pos"][0] += player["x_velocity"]
        return

    speed = player["speed"]

    # Dash handling
    if keys[pygame.K_LSHIFT]:  # Dash key is pressed
        if not player.get("dash_key_pressed", False):  # Check if it's a new press
            if pygame.time.get_ticks() - player["last_dash"] >= player["dash_cooldown"]:
                # Check if a movement key is being held
                if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
                    player["is_dashing"] = True
                    player["dash_timer"] = 15  # Dash lasts for 15 frames (adjust as needed)
                    player["x_velocity"] = player["dash_speed"]
                    player["facing_right"] = True  # Update facing direction
                    player["last_dash"] = pygame.time.get_ticks()
                elif keys[pygame.K_LEFT] or keys[pygame.K_a]:
                    player["is_dashing"] = True
                    player["dash_timer"] = 15  # Dash lasts for 15 frames (adjust as needed)
                    player["x_velocity"] = -player["dash_speed"]
                    player["facing_right"] = False  # Update facing direction
                    player["last_dash"] = pygame.time.get_ticks()

        player["dash_key_pressed"] = True  # Set the key as pressed
    else:
        player["dash_key_pressed"] = False  # Reset the key state when released

    # Horizontal movement
    if keys[pygame.K_LEFT] or keys[pygame.K_a]:
        player["pos"][0] -= speed
        player["facing_right"] = False  # Update facing direction
    if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
        player["pos"][0] += speed
        player["facing_right"] = True  # Update facing direction

    # Jumping
    if keys[pygame.K_SPACE] and player["is_grounded"]:
        player["y_velocity"] = PLAYER_STATS["jump_force"]  # Jump force



def handle_collisions(player, platforms):
    """Handles collisions between the player and platforms."""
    player["is_grounded"] = False  # Reset grounded state

    # Player's rectangle for collision detection
    player_rect = pygame.Rect(player["pos"][0], player["pos"][1], PLAYER_STATS["size"], PLAYER_STATS["size"])
    previous_bottom = player_rect.bottom - player["y_velocity"]  # Previous bottom position for swept collisions

    for platform in platforms:
        # Top collision (landing on a platform)
        if (
            previous_bottom <= platform.rect.top and
            player_rect.bottom >= platform.rect.top and
            player_rect.right > platform.rect.left and
            player_rect.left < platform.rect.right and
            player["y_velocity"] > 0
        ):
            player["pos"][1] = platform.rect.top - PLAYER_STATS["size"]  # Snap to platform top
            player["y_velocity"] = 0  # Stop vertical movement
            player["is_grounded"] = True
            break  # Stop checking once grounded

        # Bottom collision (head bumping into platform)
        elif (
            player_rect.top < platform.rect.bottom and
            player_rect.top >= platform.rect.bottom - abs(player["y_velocity"]) and  # Swept collision logic
            player_rect.right > platform.rect.left and
            player_rect.left < platform.rect.right and
            player["y_velocity"] < 0
        ):
            player["pos"][1] = platform.rect.bottom  # Snap below the platform
            player["y_velocity"] = 0  # Stop upward movement

        # Side collisions (prevent passing through platforms horizontally)
        if (
            player_rect.right > platform.rect.left and  # Right edge touches platform
            player_rect.left < platform.rect.left and  # Moving into the left side
            player_rect.bottom > platform.rect.top + 5 and  # Ignore collisions at the top edge
            player_rect.top < platform.rect.bottom - 5  # Ignore collisions at the bottom edge
        ):
            player["pos"][0] = platform.rect.left - PLAYER_STATS["size"]  # Snap to the left side
            player["x_velocity"] = 0  # Stop horizontal movement
        elif (
            player_rect.left < platform.rect.right and  # Left edge touches platform
            player_rect.right > platform.rect.right and  # Moving into the right side
            player_rect.bottom > platform.rect.top + 5 and  # Ignore collisions at the top edge
            player_rect.top < platform.rect.bottom - 5  # Ignore collisions at the bottom edge
        ):
            player["pos"][0] = platform.rect.right  # Snap to the right side
            player["x_velocity"] = 0  # Stop horizontal movement


        # Bottom collision (head bumping into platform)
        elif (
            player_rect.top < platform.rect.bottom and
            player_rect.top >= platform.rect.bottom - abs(player["y_velocity"]) and  # Swept collision check
            player_rect.right > platform.rect.left and
            player_rect.left < platform.rect.right and
            player["y_velocity"] < 0
        ):
            player["pos"][1] = platform.rect.bottom  # Snap below the platform
            player["y_velocity"] = 0  # Stop upward movement

def draw_borders(screen, camera):
    """Draws the borders of the world."""
    top_border = pygame.Rect(0, 0, WORLD_WIDTH, BORDER_THICKNESS)
    bottom_border = pygame.Rect(0, WORLD_HEIGHT - BORDER_THICKNESS, WORLD_WIDTH, BORDER_THICKNESS)
    left_border = pygame.Rect(0, 0, BORDER_THICKNESS, WORLD_HEIGHT)
    right_border = pygame.Rect(WORLD_WIDTH - BORDER_THICKNESS, 0, BORDER_THICKNESS, WORLD_HEIGHT)

    pygame.draw.rect(screen, COLORS["border"], camera.apply(top_border))
    pygame.draw.rect(screen, COLORS["border"], camera.apply(bottom_border))
    pygame.draw.rect(screen, COLORS["border"], camera.apply(left_border))
    pygame.draw.rect(screen, COLORS["border"], camera.apply(right_border))

def draw_velocity_bars(screen, player):
    """Draws X and Y velocity bars at the top-left of the screen."""
    # Bar settings
    bar_width = 200  # Max width of the bar
    bar_height = 20
    max_velocity = 20  # Max absolute velocity value for scaling

    # X Velocity Bar
    x_velocity_ratio = player["x_velocity"] / max_velocity  # Scale between -1 and 1
    x_bar_length = int(bar_width * abs(x_velocity_ratio))  # Bar length proportional to velocity
    x_bar_color = (0, 255, 0) if x_velocity_ratio >= 0 else (255, 0, 0)  # Green for positive, red for negative
    x_bar_pos = (10, 10)  # Position of X bar
    pygame.draw.rect(screen, x_bar_color, (*x_bar_pos, x_bar_length, bar_height))  # Draw the bar

    # Y Velocity Bar
    y_velocity_ratio = player["y_velocity"] / max_velocity  # Scale between -1 and 1
    y_bar_length = int(bar_width * abs(y_velocity_ratio))  # Bar length proportional to velocity
    y_bar_color = (0, 255, 0) if y_velocity_ratio >= 0 else (255, 0, 0)  # Green for positive, red for negative
    y_bar_pos = (10, 40)  # Position of Y bar
    pygame.draw.rect(screen, y_bar_color, (*y_bar_pos, y_bar_length, bar_height))  # Draw the bar

    # Labels for debugging
    font = pygame.font.SysFont(None, 24)
    x_label = font.render(f"X Velocity: {player['x_velocity']:.1f}", True, (255, 255, 255))
    y_label = font.render(f"Y Velocity: {player['y_velocity']:.1f}", True, (255, 255, 255))
    screen.blit(x_label, (10, 10 + bar_height + 5))  # Position X label below the bar
    screen.blit(y_label, (10, 40 + bar_height + 5))  # Position Y label below the bar

def load_level(filename):
    """Loads the level data from a JSON file."""
    with open(filename, 'r') as file:
        level_data = json.load(file)
    return level_data["platforms"]

def handle_coin_collection(player, coins, score):
    """Check for collisions between the player and coins."""
    player_rect = pygame.Rect(player["pos"][0], player["pos"][1], PLAYER_STATS["size"], PLAYER_STATS["size"])
    for coin in coins:
        if not coin.collected and player_rect.colliderect(coin.rect):
            coin.collected = True  # Mark coin as collected
            score += 1  # Increment the score
    return score

def handle_damage(player, amount):
    """Reduces the player's HP by the given amount."""
    player["hp"] -= amount
    if player["hp"] < 0:
        player["hp"] = 0  # Ensure HP doesn't go below 0

def draw_health_bar(screen, player):
    """Draws the player's health bar on the screen."""
    bar_width = 200
    bar_height = 20
    hp_ratio = player["hp"] / 100  # Scale HP between 0 and 1
    hp_bar_color = (255, 0, 0)  # Red for the health bar

    pygame.draw.rect(screen, hp_bar_color, (10, 40, int(bar_width * hp_ratio), bar_height))  # Draw HP bar
    font = pygame.font.SysFont(None, 24)
    hp_text = font.render(f"HP: {player['hp']}", True, (255, 255, 255))
    screen.blit(hp_text, (10, 40 + bar_height + 5))  # Text below the health bar

def handle_damage_bricks(player, damage_bricks):
    """Checks for collisions with damage bricks and applies damage."""
    player_rect = pygame.Rect(player["pos"][0], player["pos"][1], PLAYER_STATS["size"], PLAYER_STATS["size"])
    for brick in damage_bricks:
        if player_rect.colliderect(brick.rect):
            handle_damage(player, brick.damage)  # Apply damage to the player

def handle_damage(player, amount):
    """Reduces the player's HP by the given amount if not invincible."""
    current_time = pygame.time.get_ticks()
    if not player["is_invincible"]:  # Only apply damage if not invincible
        player["hp"] -= amount
        if player["hp"] < 0:
            player["hp"] = 0  # Ensure HP doesn't go below 0
        player["is_invincible"] = True  # Activate invincibility
        player["last_damage_time"] = current_time  # Record the time of damage




# === Database === #
def initialize_database():
    # Get the directory where the script is located
    script_dir = os.path.dirname(__file__)  # Directory of the running script
    db_path = os.path.join(script_dir, 'score.db')  # Full path to score.db in the same directory
    
    conn = sqlite3.connect(db_path)  # Create or open score.db at the specified path
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_name TEXT NOT NULL,
            score INTEGER NOT NULL,
            date TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def save_score(player_name, score):
    from datetime import datetime
    script_dir = os.path.dirname(__file__)  # Directory of the running script
    db_path = os.path.join(script_dir, 'score.db')  # Full path to score.db
    
    conn = sqlite3.connect(db_path)  # Connect to the database at the specified path
    cursor = conn.cursor()
    date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # Current timestamp
    cursor.execute('INSERT INTO scores (player_name, score, date) VALUES (?, ?, ?)', (player_name, score, date))
    conn.commit()
    conn.close()

def get_top_scores():
    """Fetches the top 3 scores from the database."""
    script_dir = os.path.dirname(__file__)  # Directory of the running script
    db_path = os.path.join(script_dir, 'score.db')  # Full path to score.db
    
    conn = sqlite3.connect(db_path)  # Connect to the database
    cursor = conn.cursor()
    cursor.execute('SELECT player_name, score FROM scores ORDER BY score DESC LIMIT 3')
    top_scores = cursor.fetchall()  # Fetch the top 3 scores
    conn.close()
    return top_scores

def draw_leaderboard(screen, font):
    """Displays the top 3 scores on the screen."""
    top_scores = get_top_scores()  # Fetch the top scores
    leaderboard_x = 10
    leaderboard_y = 70  # Position below the health bar

    title_text = font.render("Leaderboard:", True, (255, 255, 255))  # Title
    screen.blit(title_text, (leaderboard_x, leaderboard_y))  # Render title

    for i, (player_name, score) in enumerate(top_scores):
        score_text = font.render(f"{i + 1}. {player_name}: {score}", True, (255, 255, 255))
        screen.blit(score_text, (leaderboard_x, leaderboard_y + 30 * (i + 1)))  # Offset each entry




# === Main loops === #
def main_menu():
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    font = pygame.font.SysFont(None, 36)
    clock = pygame.time.Clock()

    # Menu variables
    player_name = ""
    input_active = False  # Tracks if the text input field is active
    play_button_rect = pygame.Rect(WINDOW_WIDTH // 2 - 75, WINDOW_HEIGHT // 2 + 50, 150, 50)  # Play button rectangle
    input_rect = pygame.Rect(WINDOW_WIDTH // 2 - 150, WINDOW_HEIGHT // 2 - 50, 300, 50)  # Input field rectangle

    running = True
    while running:
        screen.fill((0, 0, 0))  # Black background
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.MOUSEBUTTONDOWN:
                # Check if Play button is clicked
                if play_button_rect.collidepoint(event.pos) and player_name.strip():
                    return player_name  # Start the game with the entered name

                # Check if input field is clicked
                if input_rect.collidepoint(event.pos):
                    input_active = True
                else:
                    input_active = False

            if event.type == pygame.KEYDOWN and input_active:
                # Handle text input for player name
                if event.key == pygame.K_BACKSPACE:
                    player_name = player_name[:-1]  # Remove last character
                else:
                    player_name += event.unicode  # Append typed character

        # Draw input field
        pygame.draw.rect(screen, (255, 255, 255), input_rect, 2)  # White border
        name_text = font.render(player_name, True, (255, 255, 255))  # Render the player's name
        screen.blit(name_text, (input_rect.x + 10, input_rect.y + 10))  # Position text within input field

        # Draw Play button
        pygame.draw.rect(screen, (0, 255, 0), play_button_rect)  # Green button
        play_text = font.render("Play", True, (0, 0, 0))  # Black "Play" text
        screen.blit(play_text, (play_button_rect.x + 40, play_button_rect.y + 10))  # Center text on button

        # Draw leaderboard
        top_scores = get_top_scores()  # Fetch top 3 scores from the database
        leaderboard_x = WINDOW_WIDTH // 2 - 150
        leaderboard_y = WINDOW_HEIGHT // 2 + 120
        title_text = font.render("Leaderboard:", True, (255, 255, 255))  # Title
        screen.blit(title_text, (leaderboard_x, leaderboard_y))  # Render title
        for i, (name, score) in enumerate(top_scores):
            score_text = font.render(f"{i + 1}. {name}: {score}", True, (255, 255, 255))
            screen.blit(score_text, (leaderboard_x, leaderboard_y + 30 * (i + 1)))  # Offset each entry

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    return None

def main(player_name):
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    clock = pygame.time.Clock()

    # Camera setup
    camera = Camera(WORLD_WIDTH, WORLD_HEIGHT)

    # Player setup
    player = {
        "pos": PLAYER_STATS["start_pos"][:],  # Starting position (copy)
        "y_velocity": 0,
        "x_velocity": 0,
        "is_grounded": False,
        "last_dash": 0,  # Last dash timestamp
        "speed": PLAYER_STATS["speed"],  # Normal movement speed
        "dash_speed": PLAYER_STATS["dash_speed"],  # Dash speed
        "dash_cooldown": PLAYER_STATS["dash_cooldown"],  # Dash cooldown
        "is_dashing": False,  # Tracks if player is currently dashing
        "dash_timer": 0,      # Timer for dash duration
        "facing_right": True, # Tracks last facing direction (default: right)
        "dash_key_pressed": False,  # Tracks dash key state
        "hp": 100,  # Player's starting health
        "is_invincible": False,  # Tracks whether the player is invincible
        "last_damage_time": 0,   # Tracks the last time the player took damage
    }

    # Initialize coins and score
    coins = [
        Coin(300, 400),  # Example positions
        Coin(500, 500),
        Coin(600, 300),
        Coin(700, 200)
    ]
    score = 0  # Start score at 0
    font = pygame.font.SysFont(None, 36)  # Font for displaying score

    # Load platforms from JSON
    platforms_data = load_level(LEVEL_PATH)
    platforms = [Platform(data["x"], data["y"], data["width"], data["height"]) for data in platforms_data]

    # Initialize damage bricks
    damage_bricks = [
        DamageBrick(200, 150)  # Brick at (200, 150) with 25 damage
    ]

    # Game state variables
    game_over = False
    game_over_time = None
    score_saved = False  # Tracks if the score has already been saved

    running = True
    while running:
        delta_time = clock.tick(60)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        # Handle game over state
        # Handle game over state
        # Handle game over state
        if game_over:
            # Save the player's score only once
            if not score_saved:
                save_score(player_name, score)
                score_saved = True  # Mark the score as saved

            # Check if 5 seconds have passed since the game ended
            if pygame.time.get_ticks() - game_over_time > 5000:  # 5 seconds in milliseconds
                running = False  # Exit the game
            else:
                # Display the death screen
                screen.fill((0, 0, 0))  # Black background
                death_text = font.render("Game Over", True, (255, 0, 0))  # Red "Game Over" text
                score_text = font.render(f"Score: {score}", True, (255, 255, 255))  # White score text
                screen.blit(death_text, (WINDOW_WIDTH // 2 - death_text.get_width() // 2, WINDOW_HEIGHT // 2 - 50))
                screen.blit(score_text, (WINDOW_WIDTH // 2 - score_text.get_width() // 2, WINDOW_HEIGHT // 2 + 10))
                pygame.display.flip()
                continue

        # Handle input and movement
        keys = pygame.key.get_pressed()
        move_player(player, keys, delta_time)

        # Apply physics and handle collisions
        apply_physics(player)
        handle_collisions(player, platforms)
        constrain_player_to_world(player)

        # Check for player death based on HP
        if player["hp"] <= 0:
            game_over = True
            game_over_time = pygame.time.get_ticks()  # Record the time when the game ended
            continue

        # Check for collisions with damage bricks
        handle_damage_bricks(player, damage_bricks)

        # Reset invincibility after 1 second
        if player["is_invincible"]:
            if pygame.time.get_ticks() - player["last_damage_time"] > 1000:  # 1 second (1000 ms)
                player["is_invincible"] = False

        # Check for coin collection
        score = handle_coin_collection(player, coins, score)

        # Update the camera
        player_rect = pygame.Rect(player["pos"][0], player["pos"][1], PLAYER_STATS["size"], PLAYER_STATS["size"])
        camera.update(player_rect)

        # Drawing
        screen.fill(COLORS["background"])  # Clear screen
        draw_borders(screen, camera)  # Draw borders

        # Draw platforms, coins, damage bricks, and player
        player_camera_rect = camera.apply(player_rect)
        if player["is_invincible"] and pygame.time.get_ticks() % 200 < 100:  # Flash effect
            pygame.draw.rect(screen, (255, 255, 0), player_camera_rect)  # Yellow for invincibility
        else:
            pygame.draw.rect(screen, COLORS["player"], player_camera_rect)  # Normal color

        for platform in platforms:
            platform_camera_rect = camera.apply(platform.rect)
            pygame.draw.rect(screen, COLORS["platform"], platform_camera_rect)  # Draw platform
        for coin in coins:
            if not coin.collected:  # Only draw uncollected coins
                coin_camera_rect = camera.apply(coin.rect)
                pygame.draw.ellipse(screen, (255, 215, 0), coin_camera_rect)  # Gold-colored coins
        for brick in damage_bricks:
            brick_camera_rect = camera.apply(brick.rect)
            pygame.draw.rect(screen, (255, 0, 0), brick_camera_rect)  # Red damage brick

        # Render the score and health bar on the screen
        score_text = font.render(f"Score: {score}", True, (255, 255, 255))
        screen.blit(score_text, (10, 10))  # Top-left corner
        draw_health_bar(screen, player)  # Display health bar

        pygame.display.flip()

    pygame.quit()

if __name__ == "__main__":
    initialize_database()  # Ensure database is ready
    player_name = main_menu()
    if player_name:
        main(player_name)  # Pass the player's name to the game